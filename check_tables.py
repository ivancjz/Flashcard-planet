
from backend.app.db.session import SessionLocal
from sqlalchemy import text
s = SessionLocal()
rows = s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).all()
for r in rows: print(r[0])
s.close()
