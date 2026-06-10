import os
from datetime import datetime
import random
import string
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_chunky_amigurumi_retro_candy_secret_unlocked'

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "candy123"

# --- DATABASE CONFIGURATION ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///amigurumi_candy_shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- LOGIN DECORATOR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'customer_id' not in session:
            return redirect(url_for('customer_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- MODELS ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    orders = db.relationship('Order', backref='customer_user', lazy=True)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.Text)
    stock = db.Column(db.Integer, default=5)

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    tracking_code = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # guest checkout allowed
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    shipping_address = db.Column(db.Text, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, nullable=True)
    product_title = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, default=1)

# --- UTILS & SEEDING ---
def generate_tracking_code():
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"AMI-{chars}"

with app.app_context():
    db.create_all()
    if not Product.query.first():
        seed_item = Product(
            title="Strawberry Jelly Bunny",
            price=34.99,
            description="<strong>✨ Handmade with Love ✨</strong><br>This premium plush rabbit is stitched using ultra-soft pink velvet yarn.<br><br><span style='color: #E85A84;'>Features:</span> Comes with hand-embroidered facial structures and a custom strawberry blossom head crown attachment frame layer.",
            image_url="https://images.unsplash.com/photo-1559251606-c623743a6d76?q=80&w=600&auto=format&fit=crop",
            stock=8
        )
        db.session.add(seed_item)
        db.session.commit()

def is_admin():
    return session.get('is_admin') == True

# --- CORE ROUTES ---
@app.route('/')
def home():
    products = Product.query.all()
    catalog = []
    for p in products:
        imgs = [u.strip() for u in p.image_url.split(',') if u.strip()] if p.image_url else []
        main_img = imgs[0] if imgs else 'https://via.placeholder.com/300?text=No+Image'
        catalog.append({'data': p, 'main_image': main_img})
    return render_template('shop.html', catalog=catalog, is_admin=is_admin())

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    images = [u.strip() for u in product.image_url.split(',') if u.strip()] if product.image_url else []
    if not images:
        images = ['https://via.placeholder.com/600x600?text=No+Image']
    return render_template('product_detail.html', product=product, images=images, is_admin=is_admin())

@app.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    qty = int(request.form.get('quantity', 1))

    if qty > product.stock:
        return jsonify({"status": "error", "message": f"Only {product.stock} items left!"}), 400

    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']
    p_id_str = str(product_id)
    cart[p_id_str] = cart.get(p_id_str, 0) + qty
    session['cart'] = cart
    session.modified = True

    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    grand_total = 0.0

    for p_id_str, qty in cart.items():
        product = Product.query.get(int(p_id_str))
        if product:
            imgs = [u.strip() for u in product.image_url.split(',') if u.strip()] if product.image_url else []
            main_img = imgs[0] if imgs else 'https://via.placeholder.com/150'
            line_total = product.price * qty
            grand_total += line_total
            cart_items.append({
                'product': product,
                'quantity': qty,
                'line_total': line_total,
                'main_image': main_img
            })

    return render_template('cart.html', cart_items=cart_items, grand_total=grand_total, is_admin=is_admin())

@app.route('/cart/remove/<int:product_id>')
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    p_id_str = str(product_id)
    if p_id_str in cart:
        cart.pop(p_id_str)
    session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('home'))

    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()

    if not name or not phone or not address:
        return "Error: All processing fields (Name, Phone Number, Address) are strictly required.", 400

    grand_total = 0.0
    order_items_to_create = []

    for p_id_str, qty in cart.items():
        product = db.session.get(Product, int(p_id_str))
        if not product or product.stock < qty:
            return f"Error: {product.title if product else 'An item'} is out of stock!", 400

        grand_total += (product.price * qty)
        order_items_to_create.append(
            OrderItem(
                product_id=product.id,
                product_title=product.title,
                price=product.price,
                quantity=qty
            )
        )
        product.stock -= qty

    tracking = generate_tracking_code()
    new_order = Order(
        tracking_code=tracking,
        user_id=session.get('customer_id'),
        customer_name=name,
        customer_phone=phone,
        shipping_address=address,
        total_price=grand_total
    )

    for item in order_items_to_create:
        new_order.items.append(item)

    db.session.add(new_order)
    db.session.commit()

    session.pop('cart', None)
    return redirect(url_for('order_success', code=tracking))

@app.route('/order-success/<code>')
def order_success(code):
    return render_template('success.html', code=code, is_admin=is_admin())

@app.route('/track', methods=['GET', 'POST'])
def track_order():
    order = None
    searched = False
    if request.method == 'POST':
        code = request.form.get('tracking_code', '').strip().upper()
        order = Order.query.filter_by(tracking_code=code).first()
        searched = True
    return render_template('track.html', order=order, searched=searched, is_admin=is_admin())

# --- CUSTOMER AUTHENTICATION ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        password = request.form.get('password')

        if User.query.filter_by(phone=phone).first():
            error = "This phone number is already registered! 🍬"
        else:
            new_user = User(
                name=name,
                phone=phone,
                password_hash=generate_password_hash(password)
            )
            db.session.add(new_user)
            db.session.commit()

            session['customer_id'] = new_user.id
            session['customer_name'] = new_user.name
            session['customer_phone'] = new_user.phone
            return redirect(url_for('my_orders'))

    return render_template('register.html', error=error, is_admin=is_admin())

@app.route('/customer-login', methods=['GET', 'POST'])
def customer_login():
    error = None
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        user = User.query.filter_by(phone=phone).first()

        if user and check_password_hash(user.password_hash, password):
            session['customer_id'] = user.id
            session['customer_name'] = user.name
            session['customer_phone'] = user.phone
            return redirect(url_for('my_orders'))
        else:
            error = "Invalid phone number or password! 🍬"

    return render_template('customer_login.html', error=error, is_admin=is_admin())

@app.route('/customer-logout')
def customer_logout():
    session.pop('customer_id', None)
    session.pop('customer_name', None)
    session.pop('customer_phone', None)
    return redirect(url_for('home'))

@app.route('/my-orders')
@login_required
def my_orders():
    user_orders = Order.query.filter_by(user_id=session['customer_id']).order_by(Order.created_at.desc()).all()
    return render_template('my_orders.html', orders=user_orders, is_admin=is_admin())

# --- ADMIN ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_orders'))
        error = "Invalid combination! 🍬"
    return render_template('login.html', error=error, is_admin=is_admin())

@app.route('/logout')
def logout():
    session.pop('is_admin', None)
    return redirect(url_for('home'))

@app.route('/admin/orders')
def admin_orders():
    if not is_admin():
        return redirect(url_for('login'))
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin_orders.html', orders=orders, is_admin=is_admin())

@app.route('/admin/order/<int:order_id>/update', methods=['POST'])
def update_order_status(order_id):
    if not is_admin():
        abort(403)
    order = Order.query.get_or_404(order_id)
    order.status = request.form.get('status')
    db.session.commit()
    return redirect(url_for('admin_orders'))

@app.route('/admin/product/add', methods=['GET', 'POST'])
def add_product():
    if not is_admin():
        return redirect(url_for('login'))
    if request.method == 'POST':
        new_prod = Product(
            title=request.form.get('title'),
            price=float(request.form.get('price', 0.00)),
            description=request.form.get('description'),
            image_url=request.form.get('image_url'),
            stock=int(request.form.get('stock', 0))
        )
        db.session.add(new_prod)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('product_form.html', product=None, is_admin=is_admin())

@app.route('/admin/product/<int:product_id>/edit', methods=['GET', 'POST'])
def edit_product(product_id):
    if not is_admin():
        return redirect(url_for('login'))
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.title = request.form.get('title')
        product.price = float(request.form.get('price', 0.00))
        product.stock = int(request.form.get('stock', 0))
        product.image_url = request.form.get('image_url')
        product.description = request.form.get('description')
        db.session.commit()
        return redirect(url_for('product_detail', product_id=product.id))
    return render_template('product_form.html', product=product, is_admin=is_admin())

@app.route('/admin/product/<int:product_id>/delete', methods=['POST'])
def delete_product(product_id):
    if not is_admin():
        abort(403)
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for('home'))
# ၁။ Admin အတွက် User စာရင်းနှင့် Order အရေအတွက် ကြည့်ရန် Route
@app.route('/admin/users')
def admin_users():
    if not is_admin():
        return redirect(url_for('login'))
    
    # User အားလုံးကို ဆွဲထုတ်ပြီး Order အရေအတွက်ပါ တွက်ချက်ခြင်း
    users = User.query.all()
    user_data = []
    for user in users:
        user_data.append({
            'id': user.id,
            'name': user.name,
            'phone': user.phone,
            'order_count': len(user.orders) # Relationship ကိုသုံးပြီး Order အရေအတွက် ယူခြင်း
        })
    
    return render_template('admin_users.html', users=user_data, is_admin=is_admin())

# ၂။ User ကို ဖျက်ရန် Route
@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not is_admin():
        abort(403)
    user = User.query.get_or_404(user_id)
    
    # User ကိုဖျက်ရင် သူ့ရဲ့ Order တွေပါ ပြဿနာမတက်အောင် အရင်စစ်ဆေးပါ (သို့) cascade လုပ်ပါ
    # ဒီနေရာမှာတော့ ရိုးရှင်းအောင် အရင်ဖျက်လိုက်ပါမယ်
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('admin_users'))

if __name__ == '__main__':
    app.run(debug=True, port=8000)
