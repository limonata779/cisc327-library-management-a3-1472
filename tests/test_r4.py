# R4 tests for library_service.return_book_by_patron
import pytest
from datetime import datetime, timedelta
from services.library_service import return_book_by_patron

# helpers for setup
from database import (
    get_book_by_isbn,
    insert_borrow_record,
    insert_book,
    get_book_by_id,
    get_patron_borrow_count,
)

def shelve_book(*, title: str, author: str, isbn: str, total: int, avail: int) -> int:
    """Insert a book with distinctive data and return its DB id."""
    insert_book(title, author, isbn, total, avail)
    return get_book_by_isbn(isbn)["id"]

def seed_active_loan(patron_id: str, *, book_id: int, days_until_due: int = 7):
    """
    Created an active borrow (no return_date) for this patron+book. Uses days_until_due < 0 to make it overdue.
    """
    start = datetime.now() - timedelta(days=14)
    due = datetime.now() + timedelta(days=days_until_due)
    insert_borrow_record(patron_id, book_id, start, due)


def test_increments_stock_and_clears_active():
    """
    Positive valid 6 digit patron returns a book they actually hold.
    Expect success available copies +1, active loans decrease by 1.
    """
    patron = "808081"

    # One copy is out (avail=0) and belongs to patron
    book = shelve_book(
        title="Chronicles of Checkouts",
        author="A. Ledger",
        isbn="9600000001001",
        total=1,
        avail=0,
    )
    seed_active_loan(patron, book_id=book, days_until_due=3)
    before_avail = get_book_by_id(book)["available_copies"]
    before_count = get_patron_borrow_count(patron)
    ok, msg = return_book_by_patron(patron, book)
    after_avail = get_book_by_id(book)["available_copies"]
    after_count = get_patron_borrow_count(patron)
    assert ok is True
    assert ("success" in (msg or "").lower()) or ("return complete" in (msg or "").lower())
    assert after_avail == before_avail + 1
    assert after_count == max(0, before_count - 1)


@pytest.mark.parametrize("bad_patron", ["", "12345", "1234567", "12a456", " 222222 "])
def test_patron_id(bad_patron):
    """
    Negative Patron ID must be exactly 6 digits (no spaces or letters).
    """
    book = shelve_book(
        title="Finite Fields of Forgiveness",
        author="P. Irwin",
        isbn="9600000002002",
        total=1,
        avail=0,
    )
    # Someone has it out
    seed_active_loan("424242", book_id=book, days_until_due=5)
    before_avail = get_book_by_id(book)["available_copies"]
    ok, msg = return_book_by_patron(bad_patron, book)
    after_avail = get_book_by_id(book)["available_copies"]
    assert ok is False
    assert "invalid patron id" in (msg or "").lower()
    assert after_avail == before_avail == 0

def test_rejects_not_borrower():
    """
    neg, The caller must be the one who borrowed the book. book is borrowed by 777111; caller 777112 tries to return it.
    outputs failure + no change to availability.
    """
    true_borrower = "777111"
    imposter = "777112"
    book = shelve_book(
        title="Semaphore & Sympathy",
        author="M. Channel",
        isbn="9600000003003",
        total=1,
        avail=0,
    )
    seed_active_loan(true_borrower, book_id=book, days_until_due=2)
    before_avail = get_book_by_id(book)["available_copies"]
    ok, msg = return_book_by_patron(imposter, book)
    after_avail = get_book_by_id(book)["available_copies"]
    assert ok is False
    assert ("not borrowed" in (msg or "").lower()) or ("no active" in (msg or "").lower())
    assert after_avail == before_avail == 0

def test_overdue_fee_updates_stock():
    """
    Positive, Overdue return should still succeed, increment stock and report a late fee.
    """
    patron = "606066"
    book = shelve_book(
        title="Late Fees & Lattes",
        author="C. Barista",
        isbn="9600000004004",
        total=2,
        avail=1,
    )
    # loan overdue by 5 days
    seed_active_loan(patron, book_id=book, days_until_due=-5)
    before_avail = get_book_by_id(book)["available_copies"]
    ok, msg = return_book_by_patron(patron, book)
    after_avail = get_book_by_id(book)["available_copies"]
    assert ok is True
    assert after_avail == before_avail + 1

    # Not asserted the exact amount, but fee is not $0
    assert ("fee" in (msg or "").lower()) or ("$" in (msg or ""))
