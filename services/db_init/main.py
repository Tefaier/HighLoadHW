import sys
import os
# sys.path.insert(0, '/app')

sys.path.insert(0,  os.path.join(os.path.dirname(__file__), '..', '..'))
from common.database_init import init_all

main_url = os.getenv('MAIN_DATABASE_URL', 'postgresql://postgres:postgres@main_db:5432/main_db')
tracking_url = os.getenv('TRACKING_DATABASE_URL', 'postgresql://postgres:postgres@tracking_db:5432/tracking_db')

init_all(main_url, tracking_url)
print('Database initialization complete!')