from services.library_service import add_book_to_catalog
from database import get_book_by_isbn

def test_valid_insert():
    """
    positive, A normal and valid book should be accepted. This test also checks that
    the row is in the DB, total_copies == available_copies
    """
    isbn_ticket = "9425830617429"
    added, note = add_book_to_catalog("Pride and Prejudice", "Jane Austen", isbn_ticket, 3)

    # Should succeed
    assert added is True
    assert isinstance(note, str) and note

    # Should be persisted with available == total
    row = get_book_by_isbn(isbn_ticket)
    assert row is not None
    assert row["title"] == "Pride and Prejudice"
    assert row["author"] == "Jane Austen"
    assert row["total_copies"] == 3
    assert row["available_copies"] == 3


def test_title_required():
    """
    negative, Title must not be empty or whitespace only.
    We try 2 bad titles and ensure no DB row is created for either ISBN.
    """
    isbn_blank = "9817352046197"
    isbn_whitespace = "9305718642204"

    # Empty title
    ok_blank, note_blank = add_book_to_catalog("", "Mark Twain", isbn_blank, 1)
    assert ok_blank is False
    assert "title" in note_blank.lower()
    assert get_book_by_isbn(isbn_blank) is None

    # Whitespace title
    ok_ws, note_ws = add_book_to_catalog("   \n\t", "Mark Twain", isbn_whitespace, 1)
    assert ok_ws is False
    assert "title" in note_ws.lower()
    assert get_book_by_isbn(isbn_whitespace) is None


def test_isbn_length_13():
    """
    negative, ISBN must be exactly 13 characters long. tests a short and a long ISBN. Both should be rejected.
    Also checks the DB stays clean for those ISBNs.
    """
    isbn_too_short = "314159265358"     # 12
    isbn_too_long  = "27182818284590"   # 14
    ok_shorty, note_shorty = add_book_to_catalog("The Trial", "Franz Kafka", isbn_too_short, 1)
    assert ok_shorty is False
    assert "13" in note_shorty
    assert get_book_by_isbn(isbn_too_short) is None

    ok_lanky, note_lanky = add_book_to_catalog("Invisible Man", "Ralph Ellison", isbn_too_long, 1)
    assert ok_lanky is False
    assert "13" in note_lanky
    assert get_book_by_isbn(isbn_too_long) is None


def test_copies_positive_int():
    """
    negative, total_copies must be a positive integer (reject 0 and negatives).
    We check both 0 and -2. No DB rows should be created.
    """
    isbn_zero = "9098765432101"
    isbn_negative = "9654321987650"

    # Zero copies
    ok_zero, note_zero = add_book_to_catalog("One Hundred Years of Solitude", "Gabriel Garcia Marquez", isbn_zero, 0)
    assert ok_zero is False
    assert "positive" in note_zero.lower()
    assert get_book_by_isbn(isbn_zero) is None

    # Negative copies
    ok_neg, note_neg = add_book_to_catalog("Beloved", "Toni Morrison", isbn_negative, -2)
    assert ok_neg is False
    assert "positive" in note_neg.lower()
    assert get_book_by_isbn(isbn_negative) is None

def test_duplicate_isbn():
    """
    Negative, Inserting a second book with the same ISBN should fail.
    """
    isbn_clone = "9550013377777"

    first_ok, _ = add_book_to_catalog("The Great Gatsby", "F. Scott Fitzgerald", isbn_clone, 2)
    assert first_ok is True

    second_ok, second_note = add_book_to_catalog("Tender Is the Night", "F. Scott Fitzgerald", isbn_clone, 5)
    assert second_ok is False
    assert ("already" in second_note.lower()) or ("exists" in second_note.lower())


