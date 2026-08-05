from pathlib import Path
import querysaas
def test_version(): assert querysaas.__version__=='0.1.3'
def test_files():
    root=Path(__file__).parents[1]; assert (root/'src/querysaas/sql.py').exists() and (root/'src/querysaas/exceptions.py').exists()
