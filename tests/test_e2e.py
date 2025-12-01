"""
browser tests for the Library Management System. These tests use Selenium to drive a real
browser and exercise the app like a human user would:
1) Add a new book through the /add-book page and confirm it appears in the catalog table with a success message.

2) Borrow an existing book from the catalog page using a patron ID and verify the confirmation message.
"""
import requests
import subprocess
import sys
import contextlib
import time
import pytest
import os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Folder that contains app.py
project_root_dir = Path(__file__).resolve().parent.parent

# Base URL where our Flask app is served
base_app_url = "http://localhost:5000"


def wait_for_server_ready(url: str, timeout_seconds: int = 10):
    """
    Poll the given URL until the Flask server responds or timeout.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code < 500:

                # server is up
                return
        except requests.exceptions.ConnectionError:

            # Server not up yet so we wait and try again
            time.sleep(0.2)
    raise RuntimeError(f"The flask server ({url}) didn't start within {timeout_seconds} seconds")


@pytest.fixture(scope="session", autouse=True)
def start_flask_application():
    """
    Starts the flask app once for the whole test session. Removes library.db so we always start
    from the same sample data. Runs python app.py using the same interpreter that runs pytest.
    Shut the server down when tests are done.
    """

    # Starting from a fresh database each run
    database_file_path = project_root_dir / "library.db"
    if database_file_path.exists():
        database_file_path.unlink()

    # Launching app.py as a child process
    environment_variables = os.environ.copy()
    flask_process = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=str(project_root_dir),
        env=environment_variables,
    )

    wait_for_server_ready("http://127.0.0.1:5000")

    # Yielding control back to pytest as tests run here
    yield

    # The test session ends and we stop the flask process
    flask_process.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        flask_process.wait(timeout=5)
        # if it times out we fall through

    # If it’s still running force end
    if flask_process.poll() is None:
        flask_process.kill()


@pytest.fixture
def selenium_driver():
    """
    Creates a new chrome browser for each test.
    The browser runs in headless mode which means it has no visible window. If you want to see
    the browser while the test runs remove the headless option in the code below.
    """
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1280,720")
    browser = webdriver.Chrome(options=chrome_options)
    yield browser
    browser.quit()


def find_catalog_row_for_title(browser: webdriver.Chrome, book_title: str):
    """
    Returns the tr element whose text contains book_title. Fails the test if nothing matches.
    """
    rows = browser.find_elements(By.CSS_SELECTOR, "table tbody tr")
    matching_row = None
    for row in rows:
        if book_title in row.text:
            matching_row = row
            break
    assert matching_row is not None, (
        f'Couldnt find catalog row for title "{book_title}".'
    )
    return matching_row


def test_add_new_book_visible_in_catalog(selenium_driver):
    """
    add book E2E flow.
    1.Opens the add book page.
    2.Fills in fields for a new test book.
    3.Submits the form.
    4.Verifies that a success message is shown.
    5.Verifies that the new book shows up in the catalog table.
    """

    # Navigating to the add book page we go directly to /addbook
    add_book_url = f"{base_app_url}/add_book"
    selenium_driver.get(add_book_url)

    # Waiting until the title input is present to know the page loaded.
    WebDriverWait(selenium_driver, timeout=5).until(
        EC.presence_of_element_located((By.ID, "title"))
    )

    # Defining the test book data in one place. Using a dictionary makes it very clear what
    # values we're sending and lets us loop over them instead of writing 4 similar lines.
    test_book_details = {
        "title": "E2E Selenium Alt Flow Book",
        "author": "E2E tester",
        "isbn": "9990000000002",
        "total_copies": "3",
    }

    # Filling each form field with keys in the dict match the HTML element IDs in add_book.html.
    for field_id, field_value in test_book_details.items():
        input_element = selenium_driver.find_element(By.ID, field_id)

        # just in case the field has prefilled data
        input_element.clear()
        input_element.send_keys(field_value)

    # Submitting the add book form we look for the submit button using CSS selector
    submit_button = selenium_driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    submit_button.click()

    # After submitting the app redirects us back to /catalog if all went well. We wait for that redirect to happen.
    WebDriverWait(selenium_driver, timeout=5).until(
        EC.url_contains("/catalog")
    )

    # Checking that the success flash message is displayed, the app renders flash messages inside elements.
    # We wait until at least one element of the kind appears.
    success_flash_element = WebDriverWait(selenium_driver, timeout=5).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "div.flash-success"))
    )

    # Grabbing the text to assert on it.
    success_flash_text = success_flash_element.text

    # The exact message produced by library_service.add_book_to_catalog(...)
    expected_flash_text = (
        f'Book "{test_book_details["title"]}" has been successfully added to the catalog.'
    )

    # If this assert fails pytest will show the expected and actual text.
    assert expected_flash_text in success_flash_text, (
        f"Success flash message couldn't be found.\n"
        f"We expected the success in form of: {expected_flash_text}\n"
        f"But instead got: {success_flash_text}"
    )

    # Verifying the new book appears in the catalog table where we have Selenium find
    # the row where one of the td cells contains the title
    book_title = test_book_details["title"]
    row_xpath = f"//table//tr[td[contains(normalize-space(.), '{book_title}')]]"

    catalog_row = WebDriverWait(selenium_driver, timeout=5).until(
        EC.presence_of_element_located((By.XPATH, row_xpath)),
        message=f'System couldnt find a catalog for "{book_title}"'
    )

    # Getting the text content of that row so we can check all the fields
    catalog_row_text = catalog_row.text

    # The row should contain the title, author and ISBN we just submitted.
    assert test_book_details["title"] in catalog_row_text
    assert test_book_details["author"] in catalog_row_text
    assert test_book_details["isbn"] in catalog_row_text


# Test 2 focusing on borrow book from catalog and verifying confirmation

def test_borrow_book_from_catalog_shows_confirmation(selenium_driver):
    """
    XXXXXX
    """

    # I like to give the driver a more readable alias but I still keep the fixture name the same so pytest can inject it.
    browser_session = selenium_driver

    # We're opening the catalog page
    library_catalog_page_url = f"{base_app_url}/catalog"
    browser_session.get(library_catalog_page_url)

    # Identifying which book we want to borrow and find the corresponding tr element
    # in the catalog. This title comes from the sample data inserted by add_sample_data().
    sample_book_title_to_borrow = "The Great Gatsby"

    # Deciding which patron id we'll use for this test.
    # Any valid 6 digit id works as long as it passes the service validation.
    patron_identifier_for_test = "707070"

    # Getting all the rows in the catalog table body. Each should represent a single book and contain title, author,
    # ISBN, availability
    all_catalog_rows = WebDriverWait(browser_session, 5).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "table tbody tr")
        )
    )
    book_row_element = None

    # Looping over each row and picking the 1st one whose text contains our title.
    for current_row in all_catalog_rows:
        if sample_book_title_to_borrow in current_row.text:
            book_row_element = current_row
            break

    # If we still haven't found a row we fail the test with a clear message.
    assert book_row_element is not None, (
        f'Could not find a catalog row for book title "{sample_book_title_to_borrow}". '  # XXX
        f"Rows seen: {[row.text for row in all_catalog_rows]}"  # XXXX
    )

    # Filling in the patron ID. The borrow form in each row should contain an input named "patron_id".
    patron_id_input_field = book_row_element.find_element(By.NAME, "patron_id")

    # Cleaning out any preexisting text
    patron_id_input_field.clear()

    # Typing in the patron id we chose for this scenario.
    patron_id_input_field.send_keys(patron_identifier_for_test)

    # Triggering the borrow action for that specific row. In the ui the borrow button for each row is styled with .btn-success.
    # We scope the search to book_row_element so we don't accidentally click another other button on the page.
    borrow_button_for_row = book_row_element.find_element(
        By.CSS_SELECTOR, "button.btn-success"
    )
    borrow_button_for_row.click()

    # Waiting for the success flash message and verifying its content. The borrow operation triggers a flash message with CSS class
    # "flash-success".
    borrow_success_banner = WebDriverWait(browser_session, 5).until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "div.flash-success")
        )
    )

    # The exact wording of the flash message is produced in library_service.borrow_book_by_patron(...), but it should contain:
    # Successfully borrowed "The Great Gatsby". Due date: <some date>
    success_message_text = borrow_success_banner.text
    expected_phrase = f'Successfully borrowed "{sample_book_title_to_borrow}". Due date:'  # XXXX
    assert expected_phrase in success_message_text, (
        "Borrow confirmation message did not have the expected text.\n"
        f"Expected to contain: {expected_phrase}\n"
        f"Actual message: {success_message_text}"
    )
