from .federal_bank import FederalBankParser
from .paypal import PaypalParser
from .vanco import VancoParser
from .bank_of_america import BankOfAmericaParser
from .nri_account import NriParser

def get_parser_class(parser_type):
    """
    Maps the CharityBankAccount.ParserType enum to the correct parser class.
    """
    parser_map = {
        'FEDERAL': FederalBankParser,
        'PAYPAL': PaypalParser,
        'VANCO': VancoParser,
        'BOA': BankOfAmericaParser,
        'NRI': NriParser,
    }
    
    parser_class = parser_map.get(parser_type)
    
    if not parser_class:
        raise ValueError(f"No parser implemented for type: {parser_type}")
        
    return parser_class