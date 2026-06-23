import sys
from pathlib import Path

# Add project root to python path
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

from database.db import DatabaseManager, ScraperRepository
from scraper.connectors.registries.opencorporates import CompanyRegistryData
from dataclasses import asdict

def test_integration():
    print("Initializing Database Manager...")
    db_manager = DatabaseManager()
    
    print("Running database schema updates...")
    db_manager.execute_schema()
    
    repo = ScraperRepository(db_manager)
    
    # 1. Insert a test business
    test_business = {
        "business_name": "Test Integration LLC",
        "category": "Technology Solutions",
        "website": "http://testintegration.co.in",
        "google_rating": 4.5,
        "review_count": 10,
        "phone": "+91 99999 99999",
        "address": "456 Tech Park, Trivandrum, Kerala, India"
    }
    
    print(f"Inserting test business: '{test_business['business_name']}'...")
    business_id = repo.insert_business(test_business)
    if not business_id:
        print("ERROR: Failed to insert test business.")
        return False
        
    print(f"SUCCESS: Inserted business. DB ID: {business_id}")
    
    # 2. Insert company registry data
    oc_data = CompanyRegistryData(
        business_name="Test Integration LLC",
        company_number="TEST987654",
        jurisdiction="in_kl",
        jurisdiction_label="Kerala, India",
        incorporation_date="2020-10-01",
        company_status="Active",
        company_type="Private Limited Company",
        registered_address="456 Tech Park, Trivandrum, Kerala, India",
        opencorporates_url="https://opencorporates.com/companies/in/TEST987654",
        source_platform="opencorporates_test"
    )
    
    print("Inserting company registry details...")
    success = repo.insert_company_registry(business_id, asdict(oc_data))
    if not success:
        print("ERROR: Failed to insert company registry details.")
        return False
        
    print("SUCCESS: Inserted company registry details.")
    
    # 3. Verify in database
    query = "SELECT * FROM company_registry WHERE business_id = %s;"
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (business_id,))
                row = cur.fetchone()
                if row:
                    print("\n--- Verified Record in PostgreSQL Database ---")
                    print(f"ID: {row[0]}")
                    print(f"Business ID: {row[1]}")
                    print(f"Company Number: {row[2]}")
                    print(f"Jurisdiction: {row[3]}")
                    print(f"Jurisdiction Label: {row[4]}")
                    print(f"Incorporation Date: {row[5]}")
                    print(f"Status: {row[6]}")
                    print(f"Type: {row[7]}")
                    print(f"Address: {row[8]}")
                    print(f"URL: {row[9]}")
                    print(f"Source Platform: {row[10]}")
                    print(f"Error Message: {row[11]}")
                    print(f"Enriched At: {row[12]}")
                    return True
                else:
                    print("ERROR: Record not found in company_registry table.")
                    return False
    except Exception as e:
        print(f"ERROR: Verification query failed: {e}")
        return False

if __name__ == "__main__":
    success = test_integration()
    if success:
        print("\nAll database integration tests passed successfully!")
        sys.exit(0)
    else:
        print("\nDatabase integration tests failed!")
        sys.exit(1)
