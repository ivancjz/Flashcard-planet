import os, re, socket
public_host = os.environ.get('RAILWAY_SERVICE_POSTGRES_URL','')
for port in [5432, 6543, 7000]:
    try:
        s = socket.create_connection((public_host, port), timeout=5)
        print(f'PORT {port}: OPEN')
        s.close()
    except Exception as e:
        print(f'PORT {port}: {e}')
