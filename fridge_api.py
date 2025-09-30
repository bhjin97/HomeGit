from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session


# SQLite 연결
DATABASE_URL = "sqlite:///./fridge.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# 세션 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 모델 베이스
Base = declarative_base()

# ORM 모델
class ItemModel(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    price = Column(Float)
    tax = Column(Float, nullable=True)

Base.metadata.create_all(bind=engine)  # 테이블 생성

# Pydantic 모델
class Item(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    tax: Optional[float] = None

app = FastAPI(title="🍳 냉장고 속 음식 관리 API")

# DB 세션 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
from fastapi import Depends

@app.post("/items", status_code=201)
async def create_item(item: Item, db=Depends(get_db)):
    db_item = ItemModel(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    result = item.model_dump()
    if item.tax:
        result["price_with_tax"] = item.price + item.tax
    return result

@app.get("/items")
async def read_items(db=Depends(get_db)):
    items = db.query(ItemModel).all()
    return items

@app.put("/items/{item_id}")
async def update_item(item_id: int, item: Item, db=Depends(get_db)):
    db_item = db.query(ItemModel).filter(ItemModel.id == item_id).first()
    
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
        
    for key, value in item.model_dump().items():
        setattr(db_item, key, value)
    db.commit()
    db.refresh(db_item)
    return {"item_id": item_id, **item.model_dump()}

@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int, db: Session = Depends(get_db)):
    db_item = db.query(ItemModel).filter(ItemModel.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        db.delete(db_item)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # 204 No Content: 본문 없음
    return None