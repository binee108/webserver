"""
pytest fixtures for race condition integration tests

@FEAT:order-tracking @FEAT:position-tracking @COMP:test @TYPE:integration
@ISSUE:38
"""

import pytest
import sys
import os
import tempfile

# Set testing database URL BEFORE importing the app
# Use a temp file for SQLite to avoid pool parameter issues with :memory:
db_fd, db_path = tempfile.mkstemp(suffix='.db')
os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
os.environ['FLASK_ENV'] = 'testing'

# Add worktree root directory to path (parent of .test directory)
worktree_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, worktree_root)

# Add web_server/app to path for proper imports
web_server_app_path = os.path.join(worktree_root, 'web_server')
sys.path.insert(0, web_server_app_path)

from app import create_app, db
from app.models import Strategy, Account, StrategyAccount


@pytest.fixture(scope='session')
def app():
    """Create test app with isolated SQLite database"""
    app = create_app('testing')
    app.config['TESTING'] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

    # Cleanup
    import os
    if os.path.exists(db_path):
        os.close(db_fd)
        os.unlink(db_path)


@pytest.fixture(scope='function')
def test_data(app, request):
    """Setup test strategy, account, and strategy_account with unique data per test"""
    from app.models import User
    import uuid

    with app.app_context():
        # Create test user first (with unique email per test to avoid UNIQUE constraint)
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f'test_user_{unique_id}',
            email=f'test_{unique_id}@example.com'
        )
        user.set_password('test_password')
        db.session.add(user)
        db.session.flush()

        # Create test strategy with unique group_name to avoid UNIQUE constraint violation
        strategy = Strategy(
            user_id=user.id,
            name='test_race_strategy',
            description='Test strategy for race condition tests',
            group_name=f'test_group_{unique_id}',
            is_active=True
        )
        db.session.add(strategy)
        db.session.flush()

        # Create test account
        account = Account(
            user_id=user.id,
            name='test_account',
            exchange='binance',  # Use string exchange name
            public_api='test_api_key',
            secret_api='test_api_secret',
            is_active=True
        )
        db.session.add(account)
        db.session.flush()

        # Create strategy_account
        strategy_account = StrategyAccount(
            strategy_id=strategy.id,
            account_id=account.id,
            weight=1.0,      # Default weight (100% allocation)
            leverage=1.0,    # Default leverage (1x, no leverage)
            is_active=True
        )
        db.session.add(strategy_account)
        db.session.commit()

        # Return IDs only to avoid DetachedInstanceError in threading contexts
        return {
            'user_id': user.id,
            'strategy_id': strategy.id,
            'account_id': account.id,
            'strategy_account_id': strategy_account.id
        }
