"""
Library Service Module - Business Logic Functions
Contains all the core business logic for the Library Management System
"""
from services.payment_service import PaymentGateway
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from typing import Dict, List, Optional, Tuple
from database import (
    get_book_by_id, get_book_by_isbn, get_patron_borrow_count,
    insert_book, insert_borrow_record, update_book_availability,
    update_borrow_record_return_date, get_active_borrow, get_all_books,
    get_patron_borrowed_books,
    get_patron_borrow_history,
)

# Late fee policy $0.50 per overdue day
LATE_FEE_CENTS = 50


def add_book_to_catalog(title: str, author: str, isbn: str, total_copies: int) -> Tuple[bool, str]:
    """
        Add a new book to the catalog.
        Implements R1: Book Catalog Management

        Args:
            title: Book title (max 200 chars)
            author: Book author (max 100 chars)
            isbn: 13-digit ISBN
            total_copies: Number of copies (positive integer)

        Returns:
            tuple: (success: bool, message: str)
    """
    if not title or not title.strip():
        return False, "Title is required."

    if len(title.strip()) > 200:
        return False, "Title must be less than 200 characters."

    if not author or not author.strip():
        return False, "Author is required."

    if len(author.strip()) > 100:
        return False, "Author must be less than 100 characters."

    if len(isbn) != 13:
        return False, "ISBN must be exactly 13 digits."

    if not isinstance(total_copies, int) or total_copies <= 0:
        return False, "Total copies must be a positive integer."

    # Check for duplicate ISBN
    existing = get_book_by_isbn(isbn)
    if existing:
        return False, "A book with this ISBN already exists."

    # Insert new book
    success = insert_book(title.strip(), author.strip(), isbn, total_copies, total_copies)
    if success:
        return True, f'Book "{title.strip()}" has been successfully added to the catalog.'
    else:
        return False, "Database error occurred while adding the book."

def borrow_book_by_patron(patron_id: str, book_id: int) -> Tuple[bool, str]:
    """
    Allow a patron to borrow a book.
    Implements R3 as per requirements

    Args:
        patron_id: 6-digit library card ID
        book_id: ID of the book to borrow

    Returns:
        tuple: (success: bool, message: str)
    """
    # Validate patron ID
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID. Must be exactly 6 digits."

    # Check if book exists and is available
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found."

    if book["available_copies"] <= 0:
        return False, "This book is currently not available."

    if get_patron_borrow_count(patron_id) >= 5:
        return False, "You have reached the maximum borrowing limit of 5 books."

    borrow_date = datetime.now()
    due_date = borrow_date + timedelta(days=14)

    if not insert_borrow_record(patron_id, book_id, borrow_date, due_date):
        return False, "Database error occurred while creating borrow record."

    if not update_book_availability(book_id, -1):
        return False, "Database error occurred while updating book availability."

    return True, f'Successfully borrowed "{book["title"]}". Due date: {due_date.strftime("%Y-%m-%d")}.'

def return_book_by_patron(patron_id: str, book_id: int) -> Tuple[bool, str]:
    """
    Record a book return for a patron.
    Implements R4.

    Args:
        patron_id (str): 6-digit library card ID.
        book_id   (int): ID of the book being returned.

    Returns:
        Tuple[bool, str]: (ok, message). ok=True when return is saved and stock is updated.
    """
    # patron id must be six digits
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID (need 6 digits)."

    # the book has to exist
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found."

    # patron must actually have this book out
    loan = get_active_borrow(patron_id, book_id)
    if not loan:
        return False, "No active loan for this patron and book."

    # late fee if we're past the due date
    try:
        due_dt = datetime.fromisoformat(loan["due_date"])
    except Exception:

        # if we can't read the date treat it as no fee
        due_dt = None

    now = datetime.now()
    fee_cents = 0
    if due_dt is not None and now.date() > due_dt.date():
        days_over = (now.date() - due_dt.date()).days
        fee_cents = days_over * LATE_FEE_CENTS

    # write the return and bump stock
    if not update_borrow_record_return_date(patron_id, book_id, now):
        return False, "Couldn't record the return in the database."
    if not update_book_availability(book_id, +1):
        return False, "Couldn't update book availability."

    if fee_cents > 0:
        return True, f"Return complete. Late fee: ${fee_cents/100:.2f}."
    return True, "Return complete. No fee."

def calculate_late_fee_for_book(patron_id: str, book_id: int) -> Dict:
    """
    Computes the current late fee for one active loan.
    Implements R5.

    Args:
        patron_id (str): 6-digit library card ID.
        book_id   (int): Book ID.

    Returns:
        Dict: {'fee_amount': float, 'days_overdue': int, 'status': str}.

    Notes:
        Due 14 days from borrow
        $0.50/day for the first 7 overdue days, then $1/day
        Max $15.00 per book
    """
    # quick guards
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "Invalid patron ID"}
    book = get_book_by_id(book_id)
    if not book:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "Book not found"}

    # need the active borrow to read its due date
    loan = get_active_borrow(patron_id, book_id)
    if not loan:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "No active loan"}

    # days overdue
    try:
        due_dt = datetime.fromisoformat(loan["due_date"])
    except Exception:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "Invalid due date"}

    today = datetime.now().date()
    days_late = (today - due_dt.date()).days
    if days_late <= 0:
        return {"fee_amount": 0.00, "days_overdue": 0, "status": "on time"}

    # pricing for first 7 days at $0.50/day and then $1/day. cap stands at $15
    first_block = min(days_late, 7)
    later_block = max(0, days_late - 7)
    raw = first_block * 0.50 + later_block * 1.00
    fee = min(raw, 15.00)

    return {
        "fee_amount": round(fee, 2),
        "days_overdue": int(days_late),
        "status": "overdue",
    }


def search_books_in_catalog(search_term: str, search_type: str) -> List[Dict]:
    """
    Find books by title/author or by exact 13 digit ISBN.
    Implements R6.
    Args:
        search_term (str): What to look for (text or ISBN).
        search_type (str): One of "title", "author", or "isbn".
    Returns:
        List[Dict]: Catalog-shaped rows matching the query.
    """
    field = (search_type or "").strip().lower()
    query = (str(search_term) if search_term is not None else "").strip()
    if not query or field not in {"title", "author", "isbn"}:
        return []

    # ISBN must match exactly and be 13 digits
    if field == "isbn":
        if len(query) != 13 or not query.isdigit():
            return []
        hit = get_book_by_isbn(query)
        return [hit] if hit else []

    # Title/author partial and case insensitive match over the whole shelf
    shelf = get_all_books()
    needle = query.casefold()
    if field == "title":
        return [row for row in shelf if needle in (row.get("title") or "").casefold()]
    if field == "author":
        return [row for row in shelf if needle in (row.get("author") or "").casefold()]
    return []


def get_patron_status_report(patron_id: str) -> Dict:
    """
    Builds a quick status report for a patron's active loans, late fee total and history.
    Implements R7.
    Args:
        patron_id (str): 6-digit library card ID.
    Returns:
        Dict: {
            'borrowed_now': [{book_id, title, author, due_date, overdue}],
            'active_count': int,
            'late_fees': str (e.g., "1.50"),
            'history': [{book_id, title, author, borrow_date, due_date, return_date}],
            'status': 'ok' or reason
        }
    """
    pid = (patron_id or "").strip()
    if not (pid.isdigit() and len(pid) == 6):
        return {
            "borrowed_now": [],
            "active_count": 0,
            "late_fees": "0.00",
            "history": [],
            "status": "Invalid patron ID",
        }

    # Active loans
    active_rows = get_patron_borrowed_books(pid)
    borrowed_now: List[Dict] = []
    fee_total = 0.0
    for row in active_rows:
        book_id = row["book_id"]
        fee_info = calculate_late_fee_for_book(pid, book_id)
        try:
            fee_total += float(fee_info.get("fee_amount", 0.0) or 0.0)
        except (TypeError, ValueError):

            # ignores odd values
            pass

        # keeps dates readable
        due_dt = row.get("due_date")
        due_iso = due_dt.date().isoformat() if hasattr(due_dt, "date") else (str(due_dt) if due_dt else None)
        borrowed_now.append(
            {
                "book_id": book_id,
                "title": row.get("title"),
                "author": row.get("author"),
                "due_date": due_iso,
                "overdue": bool(row.get("is_overdue")),
            }
        )

    # All borrows newest first
    hist_rows = get_patron_borrow_history(pid)
    history: List[Dict] = []
    def _to_iso(val):
        if val is None:
            return None
        return val.isoformat() if hasattr(val, "isoformat") else str(val)
    for r in hist_rows:
        history.append(
            {
                "book_id": r["book_id"],
                "title": r["title"],
                "author": r["author"],
                "borrow_date": _to_iso(r.get("borrow_date")),
                "due_date": _to_iso(r.get("due_date")),
                "return_date": _to_iso(r.get("return_date")),
            }
        )
    return {
        "borrowed_now": borrowed_now,
        "active_count": len(borrowed_now),
        "late_fees": f"{fee_total:.2f}",
        "history": history,
        "status": "ok",
    }



def pay_late_fees(patron_id: str, book_id: int, payment_gateway: PaymentGateway = None) -> Tuple[bool, str, Optional[str]]:
    """
    Process payment for late fees using external payment gateway.
    
    NEW FEATURE FOR ASSIGNMENT 3: Demonstrates need for mocking/stubbing
    This function depends on an external payment service that should be mocked in tests.
    
    Args:
        patron_id: 6-digit library card ID
        book_id: ID of the book with late fees
        payment_gateway: Payment gateway instance (injectable for testing)
        
    Returns:
        tuple: (success: bool, message: str, transaction_id: Optional[str])
        
    Example for you to mock:
        # In tests, mock the payment gateway:
        mock_gateway = Mock(spec=PaymentGateway)
        mock_gateway.process_payment.return_value = (True, "txn_123", "Success")
        success, msg, txn = pay_late_fees("123456", 1, mock_gateway)
    """
    # Validate patron ID
    if not patron_id or not patron_id.isdigit() or len(patron_id) != 6:
        return False, "Invalid patron ID. Must be exactly 6 digits.", None
    
    # Calculate late fee first
    fee_info = calculate_late_fee_for_book(patron_id, book_id)
    
    # Check if there's a fee to pay
    if not fee_info or 'fee_amount' not in fee_info:
        return False, "Unable to calculate late fees.", None
    
    fee_amount = fee_info.get('fee_amount', 0.0)
    
    if fee_amount <= 0:
        return False, "No late fees to pay for this book.", None
    
    # Get book details for payment description
    book = get_book_by_id(book_id)
    if not book:
        return False, "Book not found.", None
    
    # Use provided gateway or create new one
    if payment_gateway is None:
        payment_gateway = PaymentGateway()
    
    # Process payment through external gateway
    # THIS IS WHAT YOU SHOULD MOCK IN THEIR TESTS!
    try:
        success, transaction_id, message = payment_gateway.process_payment(
            patron_id=patron_id,
            amount=fee_amount,
            description=f"Late fees for '{book['title']}'"
        )
        
        if success:
            return True, f"Payment successful! {message}", transaction_id
        else:
            return False, f"Payment failed: {message}", None
            
    except Exception as e:
        # Handle payment gateway errors
        return False, f"Payment processing error: {str(e)}", None


def refund_late_fee_payment(transaction_id: str, amount: float, payment_gateway: PaymentGateway = None) -> Tuple[bool, str]:
    """
    Refund a late fee payment (e.g., if book was returned on time but fees were charged in error).
    
    NEW FEATURE FOR ASSIGNMENT 3: Another function requiring mocking
    
    Args:
        transaction_id: Original transaction ID to refund
        amount: Amount to refund
        payment_gateway: Payment gateway instance (injectable for testing)
        
    Returns:
        tuple: (success: bool, message: str)
    """
    # Validate inputs
    if not transaction_id or not transaction_id.startswith("txn_"):
        return False, "Invalid transaction ID."
    
    if amount <= 0:
        return False, "Refund amount must be greater than 0."
    
    if amount > 15.00:  # Maximum late fee per book
        return False, "Refund amount exceeds maximum late fee."
    
    # Use provided gateway or create new one
    if payment_gateway is None:
        payment_gateway = PaymentGateway()
    
    # Process refund through external gateway
    # THIS IS WHAT YOU SHOULD MOCK IN YOUR TESTS!
    try:
        success, message = payment_gateway.refund_payment(transaction_id, amount)
        
        if success:
            return True, message
        else:
            return False, f"Refund failed: {message}"
            
    except Exception as e:
        return False, f"Refund processing error: {str(e)}"
