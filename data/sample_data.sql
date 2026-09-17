-- =====================================================================
-- sample_data.sql
-- Sample "sales_db" schema and data for the NLP Database Query Assistant.
-- Run this against a MySQL server as an admin user, then create the
-- read-only nlp_reader user shown at the bottom.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS sales_db;
USE sales_db;

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS employees;

CREATE TABLE customers (
    customer_id   INT PRIMARY KEY AUTO_INCREMENT,
    customer_name VARCHAR(100) NOT NULL,
    city          VARCHAR(100),
    country       VARCHAR(100)
);

CREATE TABLE employees (
    employee_id   INT PRIMARY KEY AUTO_INCREMENT,
    employee_name VARCHAR(100) NOT NULL,
    role          VARCHAR(100),
    hire_date     DATE
);

CREATE TABLE products (
    product_id    INT PRIMARY KEY AUTO_INCREMENT,
    product_name  VARCHAR(100) NOT NULL,
    category      VARCHAR(100),
    unit_price    DECIMAL(12, 2) NOT NULL
);

CREATE TABLE orders (
    order_id      INT PRIMARY KEY AUTO_INCREMENT,
    customer_id   INT NOT NULL,
    employee_id   INT,
    order_date    DATE NOT NULL,
    amount        DECIMAL(12, 2) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE TABLE order_items (
    order_item_id INT PRIMARY KEY AUTO_INCREMENT,
    order_id      INT NOT NULL,
    product_id    INT NOT NULL,
    quantity      INT NOT NULL,
    line_total    DECIMAL(12, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- ---------------------------------------------------------------------
-- Sample data
-- ---------------------------------------------------------------------

INSERT INTO customers (customer_name, city, country) VALUES
('Aarav Sharma', 'Mumbai', 'India'),
('Priya Iyer', 'Pune', 'India'),
('Rohan Mehta', 'Delhi', 'India'),
('Sara Khan', 'Bengaluru', 'India'),
('Vikram Rao', 'Mumbai', 'India'),
('Ananya Gupta', 'Delhi', 'India'),
('John Smith', 'New York', 'USA'),
('Emily Davis', 'Chicago', 'USA'),
('Liam Brown', 'London', 'UK'),
('Olivia Wilson', 'Manchester', 'UK');

INSERT INTO employees (employee_name, role, hire_date) VALUES
('Neha Verma', 'Sales Executive', '2022-01-10'),
('Karan Patel', 'Sales Manager', '2021-06-15'),
('Meera Nair', 'Sales Executive', '2023-03-01');

INSERT INTO products (product_name, category, unit_price) VALUES
('Wireless Mouse', 'Electronics', 799.00),
('Mechanical Keyboard', 'Electronics', 3499.00),
('Office Chair', 'Furniture', 8999.00),
('Standing Desk', 'Furniture', 15999.00),
('Notebook Set', 'Stationery', 199.00),
('Desk Lamp', 'Furniture', 1299.00),
('USB-C Hub', 'Electronics', 1599.00),
('Whiteboard', 'Stationery', 2499.00);

INSERT INTO orders (customer_id, employee_id, order_date, amount) VALUES
(1, 1, '2025-01-05', 4298.00),
(2, 2, '2025-01-12', 15999.00),
(3, 1, '2025-01-20', 998.00),
(1, 3, '2025-02-02', 8999.00),
(4, 2, '2025-02-14', 1599.00),
(5, 1, '2025-02-28', 3499.00),
(2, 3, '2025-03-03', 799.00),
(6, 2, '2025-03-10', 2499.00),
(7, 1, '2025-03-15', 8999.00),
(8, 2, '2025-04-01', 15999.00),
(9, 3, '2025-04-10', 1299.00),
(10, 1, '2025-04-18', 199.00),
(1, 2, '2025-05-02', 3499.00),
(3, 3, '2025-05-11', 799.00),
(5, 1, '2025-05-20', 8999.00),
(4, 2, '2025-06-01', 15999.00),
(6, 3, '2025-06-15', 1599.00),
(7, 1, '2025-07-01', 799.00),
(2, 2, '2025-07-14', 2499.00),
(9, 1, '2025-08-01', 3499.00);

INSERT INTO order_items (order_id, product_id, quantity, line_total) VALUES
(1, 1, 1, 799.00), (1, 2, 1, 3499.00),
(2, 4, 1, 15999.00),
(3, 5, 5, 995.00), (3, 1, 1, 3.00),
(4, 3, 1, 8999.00),
(5, 7, 1, 1599.00),
(6, 2, 1, 3499.00),
(7, 1, 1, 799.00),
(8, 6, 1, 1299.00), (8, 8, 1, 1200.00),
(9, 3, 1, 8999.00),
(10, 4, 1, 15999.00),
(11, 6, 1, 1299.00),
(12, 5, 1, 199.00),
(13, 2, 1, 3499.00),
(14, 1, 1, 799.00),
(15, 3, 1, 8999.00),
(16, 4, 1, 15999.00),
(17, 7, 1, 1599.00),
(18, 1, 1, 799.00),
(19, 8, 1, 2499.00),
(20, 2, 1, 3499.00);

-- ---------------------------------------------------------------------
-- Read-only application user
-- Run separately as a MySQL admin. Never use an admin account from
-- the application itself.
-- ---------------------------------------------------------------------
-- CREATE USER 'nlp_reader'@'%' IDENTIFIED BY 'strong_password';
-- GRANT SELECT ON sales_db.* TO 'nlp_reader'@'%';
-- FLUSH PRIVILEGES;
