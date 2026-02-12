from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import random

# إنشاء تطبيق FastAPI
app = FastAPI()

# --- إعدادات الـ CORS ---
# دي خطوة مهمة جداً عشان تسمح لصفحة الـ HTML (اللي بتعتبر موقع خارجي) 
# إنها تقدر تبعت طلبات للسيرفر بتاعك وتستقبل رد منه بدون مشاكل أمنية.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # يسمح بالاتصال من أي مكان
    allow_credentials=True,
    allow_methods=["*"], # يسمح بجميع أنواع العمليات (GET, POST, PUT, etc.)
    allow_headers=["*"], # يسمح بجميع أنواع الـ Headers
)

# --- 1. دالة الاتصال بقاعدة البيانات ---
def get_connection():
    # بننشئ اتصال بملف قاعدة البيانات، لو الملف مش موجود الـ sqlite3 هتنشئه تلقائياً
    conn = sqlite3.connect('wallet_db.db')
    return conn

# --- 2. تهيئة الجدول عند تشغيل البرنامج ---
def create_table():
    conn = get_connection()
    cursor = conn.cursor() # الموظف اللي بينفذ الأوامر
    # إنشاء جدول المحافظ لو مش موجود، فيه الـ ID والاسم والرصيد
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users_wallets (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            balance REAL DEFAULT 0.0
        )
    ''')
    conn.commit() # حفظ التغييرات
    conn.close() # قفل الاتصال

# استدعاء الدالة عشان نضمن إن الجدول جاهز أول ما السيرفر يشتغل
create_table()

# --- 3. إنشاء حساب جديد ---
@app.post("/create-account")
def create_account(username: str, initial_balance: float):
    # التأكد إن الرصيد مش بالسالب
    if initial_balance < 0:
        return {"error": "Initial balance cannot be negative"}
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # حلقة تكرار لإنشاء ID عشوائي والتأكد إنه مش مستخدم قبل كده
    while True:
        random_id = random.randint(100000, 999999) # توليد رقم من 6 خانات
        cursor.execute("SELECT id FROM users_wallets WHERE id = ?", (random_id,))
        if cursor.fetchone() is None: # لو مش موجود، يبقى الرقم ده متاح
            break
            
    # إضافة بيانات المستخدم الجديد للجدول
    cursor.execute(
        "INSERT INTO users_wallets (id, username, balance) VALUES (?, ?, ?)",
        (random_id, username, initial_balance)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Account created", "user_id": random_id, "username": username}

# --- 4. الاستعلام عن الرصيد ---
@app.get("/balance/{user_id}")
def get_balance(user_id: int):
    # التأكد إن الـ ID المكتوب طوله صح
    if not (100000 <= user_id <= 999999):
        return {"error": "Invalid ID format. Please re-enter the 6-digit ID correctly."}
        
    conn = get_connection()
    cursor = conn.cursor()
    # البحث عن المستخدم بالـ ID
    cursor.execute("SELECT username, balance FROM users_wallets WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {"status": "success", "username": user[0], "balance": user[1]}
    # لو الـ ID مش موجود في قاعدة البيانات أصلاً
    return {"error": "ID not found. Please check the ID and try writing it again."}

# --- 5. عملية الإيداع ---
@app.put("/deposit")
def deposit(user_id: int, amount: float):
    if amount <= 0:
        return {"error": "Deposit amount must be greater than zero"}
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # التأكد أولاً إن الحساب موجود قبل ما نزود الرصيد
    cursor.execute("SELECT username FROM users_wallets WHERE id = ?", (user_id,))
    if cursor.fetchone() is None:
        conn.close()
        return {"error": "ID not found. Please check it again."}
        
    # تحديث الرصيد (جمع القيمة الجديدة على القديمة)
    cursor.execute("UPDATE users_wallets SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Successfully deposited {amount}"}

# --- 6. عملية التحويل المالي ---
@app.put("/transfer")
def transfer(sender_id: int, receiver_id: int, amount: float):
    if amount <= 0: return {"error": "Amount must be positive"}
    if sender_id == receiver_id: return {"error": "Cannot transfer to yourself"}

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # 1. التأكد من وجود المرسل ومن إن رصيده كفاية
        cursor.execute("SELECT balance FROM users_wallets WHERE id = ?", (sender_id,))
        sender_data = cursor.fetchone()
        if not sender_data: return {"error": "Sender not found"}
        if sender_data[0] < amount: return {"error": "Insufficient balance"}

        # 2. التأكد من وجود المستلم
        cursor.execute("SELECT id FROM users_wallets WHERE id = ?", (receiver_id,))
        if not cursor.fetchone(): return {"error": "Receiver not found"}

        # 3. تنفيذ الخصم والإضافة (التحويل)
        cursor.execute("UPDATE users_wallets SET balance = balance - ? WHERE id = ?", (amount, sender_id))
        cursor.execute("UPDATE users_wallets SET balance = balance + ? WHERE id = ?", (amount, receiver_id))
        
        conn.commit() # حفظ العمليتين مع بعض
        return {"status": "success", "message": "Transfer completed"}
        
    except Exception:
        conn.rollback() # لو حصل أي خطأ في النص، تراجع عن كل شيء عشان الفلوس ما تضيعش
        return {"error": "Transaction failed"}
    finally:
        conn.close()
