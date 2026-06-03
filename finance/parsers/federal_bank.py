from .base_parser import BaseStatementParser
import pandas as pd 
import re

class FederalBankParser(BaseStatementParser):
    def parse(self):
        HEADER_ROWS = 20
        FOOTER_ROWS = 9
        df = pd.read_excel(
            self.file_path,
            header=HEADER_ROWS,
            usecols=['Value Date', 'Particulars', 'Tran Type', 'Tran Id', 'Withdrawals', 'Deposits']
        )
        df = df.iloc[:-FOOTER_ROWS]

        # 1. Vectorize Operations (blazing fast compared to iterrows)
        df['Withdrawals'] = pd.to_numeric(df['Withdrawals'], errors='coerce').fillna(0)
        df['Deposits'] = pd.to_numeric(df['Deposits'], errors='coerce').fillna(0)
        
        # Calculate amount for entire column at once
        df['amount'] = df['Deposits'] - df['Withdrawals']

        # Format dates for entire column at once and drop bad rows early
        df['transaction_date'] = pd.to_datetime(df['Value Date'], errors='coerce').dt.strftime('%Y-%m-%d')
        df = df.dropna(subset=['transaction_date'])

        # 2. Avoid iterrows by converting to standard python dictionaries
        records = df.to_dict('records')
        parsed_data = []

        for row in records:
            raw_narration = str(row.get('Particulars', '')).strip()
            tran_type = str(row.get('Tran Type', '')).strip().upper()
            bank_reference = str(row.get('Tran Id', '')).strip()

            extracted_identifier = ''
            extracted_name = ''

            # Extractor logic based on Tran Type
            if raw_narration:
                desc_split = raw_narration.split('/')

                if tran_type == 'MB':
                    if len(desc_split) > 2:
                        extracted_name = desc_split[2]

                elif tran_type == 'UPI':
                    if len(desc_split) > 2:
                        extracted_identifier = desc_split[2]
                        # Extract characters until a non-alpha character is seen
                        match = re.match(r'^([A-Za-z]+)', extracted_identifier)
                        if match:
                            extracted_name = match.group(1)

                elif tran_type in ['IB', 'NEFT']:
                    if len(desc_split) > 1:
                        extracted_name = desc_split[1]

                elif tran_type == 'IMPS':
                    if len(desc_split) > 3:
                        extracted_name = desc_split[3]

                elif tran_type == 'TFR':
                    # Remove the first 5 characters of the description
                    extracted_name = raw_narration[5:]

            parsed_data.append({
                'transaction_date': row['transaction_date'],
                'amount': row['amount'],
                'bank_reference': bank_reference,
                'raw_narration': raw_narration,
                'transaction_mode': tran_type,
                'extracted_identifier': extracted_identifier.strip(),
                'extracted_name': extracted_name.strip()
            })

        return parsed_data
