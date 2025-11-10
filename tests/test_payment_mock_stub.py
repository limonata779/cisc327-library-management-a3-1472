from unittest.mock import Mock
from datetime import datetime, timedelta
from services.payment_service import PaymentGateway
from services.library_service import pay_late_fees, refund_late_fee_payment, add_book_to_catalog, return_book_by_patron
# pay_late_fees required tests

def test_successful_payment(mocker):
    # Test successful payment
    def fake_fee_calc(patron_id, book_id):

        # stub for this scenario
        assert patron_id == "121212"
        assert book_id == 99
        return {"fee_amount": 15, "days_overdue": 20, "status": "ok"}
    fee_calc_stub = mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        side_effect=fake_fee_calc,
    )
    book_lookup_stub = mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"title": "The tests"},
    )
    gateway_double = Mock(spec=PaymentGateway)
    gateway_double.process_payment.return_value = (True, "OX_422", "All good")
    ok, msg, tx_id = pay_late_fees("121212", 99, payment_gateway=gateway_double)

    # Basic result check
    assert ok is True
    assert tx_id == "OX_422"
    assert msg == "Payment successful! All good"

    # Stubs and mock verified using the required assert_called* helpers
    fee_calc_stub.assert_called_with("121212", 99)
    book_lookup_stub.assert_called_with(99)
    gateway_double.process_payment.assert_called_with(
        patron_id="121212",
        amount=15,
        description="Late fees for 'The tests'",
    )

def test_payment_declined_by_gateway(mocker):
    # Test payment declined by gateway
    fee_calc_stub = mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 5.00, "days_overdue": 2, "status": "ok"},
    )
    book_lookup_stub = mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"title": "Can't charge me"},
    )
    gateway_double = Mock(spec=PaymentGateway)
    gateway_double.process_payment.return_value = (False, None, "Card declined")
    ok, msg, tx_id = pay_late_fees("778899", 7, payment_gateway=gateway_double)
    # Sanity check
    assert ok is False
    assert tx_id is None
    assert msg == "Payment failed: Card declined"
    fee_calc_stub.assert_called_with("778899", 7)
    book_lookup_stub.assert_called_with(7)
    gateway_double.process_payment.assert_called_once()
    gateway_double.process_payment.assert_called_with(
        patron_id="778899",
        amount=5.00,
        description="Late fees for 'Can't charge me'",
    )


def test_invalid_patron_id_verify_mock_not_called(mocker):
    # Test invalid patron ID (verifies mock not called)
    fee_calc_stub = mocker.patch(
        "services.library_service.calculate_late_fee_for_book"
    )
    book_lookup_stub = mocker.patch(
        "services.library_service.get_book_by_id"
    )
    gateway_double = Mock(spec=PaymentGateway)
    ok, msg, tx_id = pay_late_fees("55!?55", 99, payment_gateway=gateway_double)

    # Sanity check
    assert ok is False
    assert tx_id is None
    assert msg == "Invalid patron ID. Must be exactly 6 digits."
    fee_calc_stub.assert_not_called()
    book_lookup_stub.assert_not_called()
    gateway_double.process_payment.assert_not_called()


def test_zero_late_fees_verify_mock_not_called(mocker):
    fee_calc_stub = mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 0.0, "days_overdue": 0, "status": "ok"},
    )
    book_lookup_stub = mocker.patch(
        "services.library_service.get_book_by_id"
    )
    gateway_double = Mock(spec=PaymentGateway)
    ok, msg, tx_id = pay_late_fees("549821", 777, payment_gateway=gateway_double)
    assert ok is False
    assert tx_id is None
    assert msg == "No late fees to pay for this book."
    fee_calc_stub.assert_called_with("549821", 777)
    book_lookup_stub.assert_not_called()
    gateway_double.process_payment.assert_not_called()


def test_network_error_exception_handling(mocker):
    # Test network error exception handling.
    fee_calc_stub = mocker.patch(
        "services.library_service.calculate_late_fee_for_book",
        return_value={"fee_amount": 6.5, "days_overdue": 2, "status": "ok"},
    )
    book_lookup_stub = mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"title": "CISC327 Book"},
    )
    gateway_double = Mock(spec=PaymentGateway)
    gateway_double.process_payment.side_effect = Exception("Gateway timeout")

    ok, msg, tx_id = pay_late_fees("000000", 65, payment_gateway=gateway_double)
    assert ok is False
    assert tx_id is None
    assert msg.startswith("Payment processing error: ")
    assert "Gateway timeout" in msg
    fee_calc_stub.assert_called_with("000000", 65)
    book_lookup_stub.assert_called_with(65)
    gateway_double.process_payment.assert_called_with(
        patron_id="000000",
        amount=6.5,
        description="Late fees for 'CISC327 Book'",
    )



# refund_late_fee_payment required tests

def test_successful_refund():
    # Test successful refund
    gateway_double = Mock(spec=PaymentGateway)
    gateway_double.refund_payment.return_value = (True, "Reversal accepted")

    ok, msg = refund_late_fee_payment(
        "txn_1", 9.75, payment_gateway=gateway_double
    )

    assert ok is True
    assert msg == "Reversal accepted"
    gateway_double.refund_payment.assert_called_with("txn_1", 9.75)


def test_invalid_transaction_id_rejection():
    # Test invalid transaction ID rejection
    gateway_double = Mock(spec=PaymentGateway)
    ok, msg = refund_late_fee_payment(
        "receipt_404", 4.20, payment_gateway=gateway_double
    )
    assert ok is False
    assert msg == "Invalid transaction ID."
    gateway_double.refund_payment.assert_not_called()


def test_invalid_refund_amount_negative():
    # Test invalid refund amounts (negative)
    gateway_double = Mock(spec=PaymentGateway)

    ok, msg = refund_late_fee_payment(
        "txn_2", -3.15, payment_gateway=gateway_double
    )
    assert ok is False
    assert msg == "Refund amount must be greater than 0."
    gateway_double.refund_payment.assert_not_called()


def test_invalid_refund_amount_zero():
    # Test invalid refund amounts (zero)
    gateway_double = Mock(spec=PaymentGateway)

    ok, msg = refund_late_fee_payment(
        "txn_3", 0.0, payment_gateway=gateway_double
    )
    assert ok is False
    assert msg == "Refund amount must be greater than 0."
    gateway_double.refund_payment.assert_not_called()


def test_invalid_refund_amount_exceeds_15_maximum():
    # Test invalid refund amounts (exceeds $15 maximum)
    gateway_double = Mock(spec=PaymentGateway)
    ok, msg = refund_late_fee_payment(
        "txn_4", 19.25, payment_gateway=gateway_double
    )
    assert ok is False
    assert msg == "Refund amount exceeds maximum late fee."
    gateway_double.refund_payment.assert_not_called()


# Additional tests to reach 80%+ coverage

def test_refund_uses_default_payment_gateway_when_none(mocker):
    # If no gateway is passed in the function should construct PaymentGateway() and use it.
    # Arranges stub out PaymentGateway() so we don't hit the real class
    gateway_double = Mock(spec=PaymentGateway)
    gateway_double.refund_payment.return_value = (True, "Reversal is accepted")
    gateway_cls_stub = mocker.patch(
        "services.library_service.PaymentGateway",
        return_value=gateway_double,
    )

    # call without the payment_gateway argument
    ok, msg = refund_late_fee_payment("txn_50", 5.00)

    # Asserts our stubbed class was used and the happy-path result is returned
    assert ok is True
    assert msg == "Reversal is accepted"
    gateway_cls_stub.assert_called_with()
    gateway_double.refund_payment.assert_called_with("txn_50", 5.00)


def test_refund_gateway_returns_false():
    # Gateway returns (False, message) and the helper should give 'Refund failed'
    gateway_double = Mock(spec=PaymentGateway)
    gateway_double.refund_payment.return_value = (False, "Card expired")
    ok, msg = refund_late_fee_payment(
        "txn_110", 7.00, payment_gateway=gateway_double
    )

    # Asserts status is False and the error text is wrapped correctly
    assert ok is False
    assert msg == "Refund failed: Card expired"
    gateway_double.refund_payment.assert_called_with("txn_110", 7.00)


def test_refund_gateway_exception_wrapped():
    # Any exception from the gateway should be linked to a Refund processing error message
    # simulate a noisy third-party gateway raising exception
    gateway_double = Mock(spec=PaymentGateway)
    gateway_double.refund_payment.side_effect = Exception("Gateway offline")
    ok, msg = refund_late_fee_payment(
        "txn_765", 5.00, payment_gateway=gateway_double
    )
    # Asserts we get a clean error string instead of a traceback
    assert ok is False
    assert msg.startswith("Refund processing error: ")
    assert "Gateway offline" in msg
    gateway_double.refund_payment.assert_called_with("txn_765", 5.00)


def test_title_over_200_chars():
    # Title longer than 200 chars should be rejected
    wordy_title = "A" * 201
    ok, msg = add_book_to_catalog(
        title=wordy_title,
        author="A story",
        isbn="9876543210123",
        total_copies=3,
    )
    assert ok is False
    assert msg == "Title must be less than 200 characters."


def test_author_whitespace_only():
    # Author made of spaces should trigger the Author is required path.
    ok, msg = add_book_to_catalog(
        title="Whitespaces    ",
        author="                   ",
        isbn="3210987654321",
        total_copies=1,
    )
    assert ok is False
    assert msg == "Author is required."


def test_author_over_100_chars():
    # Very long author name should hit the >100 chars guard.
    long_pen_name = "Dr. " + ("Z" * 101)
    ok, msg = add_book_to_catalog(
        title="A shorter Title",
        author=long_pen_name,
        isbn="5556667778889",
        total_copies=2,
    )
    assert ok is False
    assert msg == "Author must be less than 100 characters."


def test_book_missing_book(mocker):
    # get_book_by_id() returns None 'Book not found.' branch
    book_lookup_stub = mocker.patch(
        "services.library_service.get_book_by_id",
        return_value=None,
    )
    loan_stub = mocker.patch("services.library_service.get_active_borrow")
    ok, msg = return_book_by_patron("909191", 444)
    assert ok is False
    assert msg == "Book not found."
    book_lookup_stub.assert_called_once_with(444)
    loan_stub.assert_not_called()


def test_no_active_loan_patron(mocker):
    # Book exists but get_active_borrow() returns None
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 444, "title": "Ghost Loan"},
    )
    active_stub = mocker.patch(
        "services.library_service.get_active_borrow",
        return_value=None,
    )
    ok, msg = return_book_by_patron("828282", 444)
    assert ok is False
    assert msg == "No active loan for this patron and book."
    active_stub.assert_called_once_with("828282", 444)

def test_fails_when_record_update_fails(mocker):
    # update_borrow_record_return_date() returns false first DB error branch.
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 333, "title": "Return Glitch"},
    )
    past_due = (datetime.now() - timedelta(days=2)).isoformat()
    mocker.patch(
        "services.library_service.get_active_borrow",
        return_value={"due_date": past_due},
    )
    record_stub = mocker.patch(
        "services.library_service.update_borrow_record_return_date",
        return_value=False,
    )
    stock_stub = mocker.patch(
        "services.library_service.update_book_availability",
        return_value=True,
    )
    ok, msg = return_book_by_patron("414141", 333)
    assert ok is False
    assert msg == "Couldn't record the return in the database."
    record_stub.assert_called_once_with("414141", 333, mocker.ANY)
    stock_stub.assert_not_called()


def test_stock_update_fails(mocker):
    # Record update succeeds but stock update fails which should trigger second db error branch.
    mocker.patch(
        "services.library_service.get_book_by_id",
        return_value={"id": 909, "title": "Inventory Trouble"},
    )
    ok_due = (datetime.now() - timedelta(days=1)).isoformat()
    mocker.patch(
        "services.library_service.get_active_borrow",
        return_value={"due_date": ok_due},
    )
    record_stub = mocker.patch(
        "services.library_service.update_borrow_record_return_date",
        return_value=True,
    )
    stock_stub = mocker.patch(
        "services.library_service.update_book_availability",
        return_value=False,
    )
    ok, msg = return_book_by_patron("565656", 909)
    assert ok is False
    assert msg == "Couldn't update book availability."
    record_stub.assert_called_once()
    stock_stub.assert_called_once_with(909, +1)
