# Billing API (FastAPI, SQLModel, SQLite)

A backend **billing and subscription management API** built with FastAPI and SQLModel. It models real-world concepts like plans, subscriptions, and invoices with proper data integrity, soft deletes, and ownership checks.

## Tech Stack

- **Language**: Python
- **Framework**: FastAPI
- **ORM**: SQLModel (SQLAlchemy + Pydantic)
- **Database**: SQLite (local dev)
- **Other**: Uvicorn

## Features

### Plans
- Create, list, fetch, and soft-delete subscription plans.
- Unique plan names enforced at the database level.
- Fields: name, price, billing_cycle (monthly/annual), trial_days, is_active.

### Subscriptions
- Subscribe a customer to a plan.
- Tracks trial periods, status, and billing dates.
- Locks price at time of subscription ('price_at_subscription') so price changes on the plan do not affect existing subscribers.
- Fields: customer_id, plan_id, status ('trialing', 'active', 'cancelled'), start_date, end_date, trial_end_date, cancelled_at.

### Invoices
- Generate invoices for active subscriptions.
- Calculates tax and total amount.
- Enforces ownership: invoices can only be created for subscriptions owned by the customer.
- Supports payment and cancellation flows.
- Fields: invoice_number, customer_id, subscription_id, status ('open', 'paid', 'cancelled'), subtotal, tax_amount, total_amount, invoice_date, due_date, cancelled_at.

## API Overview

### Plans

- 'POST /plans/'  
  Create a new plan.

- 'GET /plans/'  
  List all plans.

- 'GET /plans/{plan_id}'  
  Get a single plan.

- 'DELETE /plans/{plan_id}'  
  Soft-delete (deactivate) a plan.

### Subscriptions

- 'POST /subscriptions/'  
  Create a subscription for a customer and plan.  
  Status: 'trialing' if the plan has trial days, otherwise 'active'.

- 'GET /subscriptions/{subscription_id}'  
  Get a subscription by id.

- 'GET /subscriptions/customer/{customer_id}'  
  List all subscriptions for a customer.

- 'DELETE /subscriptions/{subscription_id}'  
  Cancel a subscription (sets status to 'cancelled' and records 'cancelled_at').

### Invoices

- 'POST /invoices/'  
  Create an invoice for an **active** subscription.  
  - Derives 'customer_id' from the subscription and verifies ownership.  
  - Calculates 'subtotal' from 'price_at_subscription'.  
  - Applies a flat 10% tax and computes 'total_amount'.  
  - Sets 'invoice_date' to now and 'due_date' to 30 days later.

- 'GET /invoices/{invoice_id}'  
  Get a single invoice.

- 'GET /invoices/customer/{customer_id}'  
  List all invoices for a customer.

- 'PUT /invoices/{invoice_id}/pay'  
  Mark an 'open' invoice as 'paid'.

- 'DELETE /invoices/{invoice_id}'  
  Cancel an invoice (sets status to 'cancelled' and 'cancelled_at').

## Running Locally

### 1. Clone the repository

'''bash
git clone https://github.com/shivamchaudhary9/billing-api.git
cd billing-api
