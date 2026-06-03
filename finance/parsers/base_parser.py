class BaseStatementParser:
    def __init__(self, file_path):
        self.file_path = file_path

    def parse(self):
        """
        Must read the Excel file and return a list of dictionaries.
        Each dictionary must match the fields of the BankTransaction model.
        """
        raise NotImplementedError("Subclasses must implement the parse() method.")