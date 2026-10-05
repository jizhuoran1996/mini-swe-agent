-- Consumer semantics executed by the driver against the freshly installed
-- server, kept in-repo for audit.  Expected aggregate: 3 rows, qty 6, 30.50
-- (row 99 is rolled back and must not exist).

CREATE DATABASE shop;
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

SELECT COUNT(*), SUM(qty), SUM(amount) FROM shop.orders;
SHOW ENGINES;
