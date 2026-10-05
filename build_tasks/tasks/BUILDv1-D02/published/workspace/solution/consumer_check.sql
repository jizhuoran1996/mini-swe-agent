-- Independent consumer semantics reused by the driver (kept in-repo for audit).
-- A 3-row orders table is written, one row is rolled back, then dumped and
-- restored into a second, freshly initialised datadir.

CREATE DATABASE IF NOT EXISTS shop;
CREATE TABLE shop.orders (
  id INT PRIMARY KEY,
  qty INT NOT NULL,
  amount DECIMAL(10,2) NOT NULL
) ENGINE=InnoDB;

START TRANSACTION;
INSERT INTO shop.orders VALUES (1, 2, 10.00), (2, 3, 15.50);
COMMIT;

START TRANSACTION;
INSERT INTO shop.orders VALUES (99, 1, 0.01);
ROLLBACK;

INSERT INTO shop.orders VALUES (3, 1, 5.00);

-- Expected: 3, 6, 30.50
SELECT COUNT(*), SUM(qty), SUM(amount) FROM shop.orders;
