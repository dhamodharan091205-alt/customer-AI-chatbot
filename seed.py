from app.db import SessionLocal
from app.seed import seed
with SessionLocal() as db: seed(db)
print("Synthetic seed completed; existing customer and invoice rows are not duplicated.")
