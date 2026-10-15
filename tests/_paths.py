"""Where the tests find the FY2025 workbook (the same lookup the dashboard uses)."""
import config


def workbook():
    p = config.find_data_file("actuals")
    if p is None:
        raise FileNotFoundError(f"Put {config.ACTUALS_XLSX} in {config.DATA_DIR} to run these tests.")
    return str(p)
