from sqlmodel import SQLModel, Field, select, Session, create_engine
from typing import Optional, List, Annotated
from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from uuid import uuid4


class Plan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str  = Field(unique=True)                       # "Basic", "Pro", "Enterprise"
    price: float
    billing_cycle: str = "monthly"     # "monthly" or "annual"
    trial_days: int = 0
    is_active: bool = True

class PlanCreate(SQLModel):
    name: str
    price: float
    billing_cycle: str = "monthly"
    trial_days: int = 0

DATABASE_URL = "sqlite:///./plans.db"
engine = create_engine(DATABASE_URL, echo=True)
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield
app = FastAPI(lifespan=lifespan)


def get_session():
    with Session(engine) as session:
        yield session
SessionDep=Annotated[Session, Depends(get_session)]

@app.post("/plans/", response_model=Plan)
def create_plan(plan: PlanCreate, session: SessionDep):
    db_plan = Plan(**plan.model_dump())
    session.add(db_plan)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Plan with this name already exists")
    session.refresh(db_plan)
    return db_plan


@app.get("/plans/", response_model=List[Plan])
def read_plans(session: SessionDep):
    plans = session.exec(select(Plan)).all()
    return plans


@app.get("/plans/{plan_id}", response_model=Plan)
def read_plan(plan_id: int, session: SessionDep):
    plan = session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@app.delete("/plans/{plan_id}",response_model=dict)
def delete_plan(plan_id: int, session: SessionDep):
    plan = session.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan.is_active = False
    session.commit()
    return {"detail": "Plan deactivated"}

class Subscription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True, unique=True)
    customer_id: int = Field(index=True) # foreign_key="customer.id" where customer table is not defined, we just use an integer for simplicity
    plan_id: int = Field(index=True, foreign_key="plan.id")
    status: str
    price_at_subscription: float = Field(default=0.0)
    start_date: datetime
    end_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

class SubscriptionCreate(SQLModel):
    customer_id: int
    plan_id: int


@app.post("/subscriptions/", response_model=Subscription)
def create_subscription(subscription: SubscriptionCreate, session: SessionDep):
    plan = session.get(Plan, subscription.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")
    now = datetime.now()
    db_subscription = Subscription(
        customer_id=subscription.customer_id,
        plan_id=subscription.plan_id,
        start_date=now,
        trial_end_date=now + timedelta(days=plan.trial_days) if plan.trial_days > 0 else None,
        status="active" if plan.trial_days == 0 else "trialing",
        price_at_subscription=plan.price,
        end_date=now + timedelta(days=30) if plan.billing_cycle == "monthly" else now + timedelta(days=365) # For simplicity, we set end_date for monthly plans only
    )
    session.add(db_subscription)
    session.commit()
    session.refresh(db_subscription)
    return db_subscription


@app.get("/subscriptions/customer/{customer_id}", response_model=List[Subscription])
def read_subscriptions_by_customer(customer_id: int, session: SessionDep):
    subscriptions = session.exec(select(Subscription).where(Subscription.customer_id == customer_id)).all()
    return subscriptions


@app.get("/subscriptions/{subscription_id}", response_model=Subscription)
def read_subscription(subscription_id: int, session: SessionDep):
    subscription = session.get(Subscription, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription


@app.delete("/subscriptions/{subscription_id}", response_model=dict)
def cancel_subscription(subscription_id: int, session: SessionDep):
    subscription = session.get(Subscription, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    subscription.status = "cancelled"
    subscription.cancelled_at = datetime.now()
    session.commit()
    return {"detail": "Subscription cancelled"}


class Invoice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True, unique=True)
    invoice_number: str = Field(unique=True)
    customer_id: int = Field(index=True) # foreign_key="customer.id" where customer table is not defined, we just use an integer for simplicity
    subscription_id: int = Field(index=True, foreign_key="subscription.id")
    status: str   
    subtotal: float
    tax_amount: float
    total_amount: float
    invoice_date: datetime
    due_date: datetime
    cancelled_at: Optional[datetime] = None


def generate_invoice_number() -> str:
    return f"INV-{uuid4().hex[:8].upper()}"

class InvoiceCreate(SQLModel):
    customer_id: int
    subscription_id: int
    

@app.post("/invoices/", response_model=Invoice)
def create_invoice(invoice: InvoiceCreate, session: SessionDep):
    subscription = session.get(Subscription, invoice.subscription_id)
    # Only invoice active subscriptions — trialing subscriptions are invoiced
    # automatically when the trial converts to active (future enhancement)
    if not subscription or subscription.status != "active":
        raise HTTPException(status_code=404, detail="Active subscription not found")
    if subscription.customer_id != invoice.customer_id:
        raise HTTPException(status_code=400, detail="Subscription does not belong to the customer")
    subtotal = subscription.price_at_subscription
    tax_amount = round(subtotal * 0.1, 2) # Assuming a flat 10% tax rate
    total_amount = subtotal + tax_amount
    now = datetime.now()
    db_invoice = Invoice(
        invoice_number=generate_invoice_number(session),
        customer_id=invoice.customer_id,
        subscription_id=invoice.subscription_id,
        status="open",
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
        invoice_date=now,
        due_date=now + timedelta(days=30) # Payment due in 30 days
    )
    session.add(db_invoice)
    session.commit()
    session.refresh(db_invoice)
    return db_invoice
    
@app.get("/invoices/customer/{customer_id}", response_model=List[Invoice])
def read_invoices_by_customer(customer_id: int, session: SessionDep):
    invoices = session.exec(select(Invoice).where(Invoice.customer_id == customer_id)).all()
    return invoices


@app.get("/invoices/{invoice_id}", response_model=Invoice)
def read_invoice(invoice_id: int, session: SessionDep):
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.put("/invoices/{invoice_id}/pay", response_model=Invoice)
def pay_invoice(invoice_id: int, session: SessionDep):
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != "open":
        raise HTTPException(status_code=400, detail="Invoice is not open for payment")
    invoice.status = "paid"
    session.commit()
    return invoice


@app.delete("/invoices/{invoice_id}", response_model=dict)
def cancel_invoice(invoice_id: int, session: SessionDep):
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = "cancelled"
    invoice.cancelled_at = datetime.now()
    session.commit()
    return {"detail": "Invoice cancelled"}