import os
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import (
    LoginManager, UserMixin, current_user, login_required, login_user, logout_user
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from services.matching import score_items

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "private_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(ROOT / "instance" / "fastfind.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(20), unique=True, nullable=False, default=lambda: "USR-" + secrets.token_hex(4).upper())
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(20), unique=True, nullable=False, default=lambda: "ITM-" + secrets.token_hex(5).upper())
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)  # lost or found
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), nullable=False)
    color = db.Column(db.String(40), nullable=False)
    location = db.Column(db.String(160), nullable=False)
    item_date = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(1000), nullable=False)
    image_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lost_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False)
    found_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="possible", nullable=False)
    __table_args__ = (db.UniqueConstraint("lost_id", "found_id", name="unique_item_match"),)


class Claim(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    claimant_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    proof_text = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_match_member(match):
    lost = db.session.get(Item, match.lost_id)
    found = db.session.get(Item, match.found_id)
    return lost and found and current_user.id in {lost.owner_id, found.owner_id}


def make_matches(item):
    other_kind = "found" if item.kind == "lost" else "lost"
    other_items = Item.query.filter_by(kind=other_kind).all()
    for other in other_items:
        lost = item if item.kind == "lost" else other
        found = other if item.kind == "lost" else item
        if lost.owner_id == found.owner_id:
            continue
        score = score_items(lost, found, UPLOAD_DIR)
        # Threshold intentionally broad; users/admin must verify actual ownership.
        if score >= 25:
            existing = Match.query.filter_by(lost_id=lost.id, found_id=found.id).first()
            if not existing:
                db.session.add(Match(lost_id=lost.id, found_id=found.id, score=score))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Name, valid email and password (at least 8 characters) are required.", "error")
        elif User.query.filter_by(email=email).first():
            flash("This email is already registered.", "error")
        else:
            admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
            role = "admin" if admin_email and email == admin_email else "user"
            user = User(name=name, email=email, password_hash=generate_password_hash(password), role=role)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created. Welcome to Fast Find AI!", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    lost_items = Item.query.filter_by(owner_id=current_user.id, kind="lost").order_by(Item.created_at.desc()).all()
    found_items = Item.query.filter_by(owner_id=current_user.id, kind="found").order_by(Item.created_at.desc()).all()
    matches = Match.query.join(Item, Match.lost_id == Item.id).filter(
        (Item.owner_id == current_user.id)
    ).all()
    found_matches = Match.query.join(Item, Match.found_id == Item.id).filter(
        (Item.owner_id == current_user.id)
    ).all()
    match_map = {m.id: m for m in matches + found_matches}
    return render_template("dashboard.html", lost_items=lost_items, found_items=found_items, matches=list(match_map.values()))


@app.route("/report/<kind>", methods=["GET", "POST"])
@login_required
def report(kind):
    if kind not in {"lost", "found"}:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        color = request.form.get("color", "").strip()
        location = request.form.get("location", "").strip()
        item_date = request.form.get("item_date", "").strip()
        description = request.form.get("description", "").strip()
        image = request.files.get("image")
        if not all([title, category, color, location, item_date, description]):
            flash("Please fill in all required fields.", "error")
            return render_template("report.html", kind=kind)
        filename = None
        if image and image.filename:
            if not allowed_file(image.filename):
                flash("Image must be PNG, JPG, JPEG or WEBP.", "error")
                return render_template("report.html", kind=kind)
            filename = secrets.token_hex(16) + "_" + secure_filename(image.filename)
            image.save(UPLOAD_DIR / filename)
        item = Item(
            owner_id=current_user.id, kind=kind, title=title, category=category,
            color=color, location=location, item_date=item_date,
            description=description, image_filename=filename
        )
        db.session.add(item)
        db.session.flush()
        make_matches(item)
        db.session.commit()
        flash("Report saved. Found reports are private; potential matches are shared only with the two report owners.", "success")
        return redirect(url_for("dashboard"))
    return render_template("report.html", kind=kind)


@app.route("/matches")
@login_required
def matches_page():
    # Only show matches where the current user owns one of the two reports.
    all_matches = Match.query.order_by(Match.score.desc()).all()
    visible = [m for m in all_matches if is_match_member(m)]
    return render_template("matches.html", matches=visible)


@app.route("/match/<int:match_id>/claim", methods=["POST"])
@login_required
def claim(match_id):
    match = db.session.get(Match, match_id)
    if not match or not is_match_member(match):
        abort(404)
    lost = db.session.get(Item, match.lost_id)
    if current_user.id != lost.owner_id:
        abort(403)
    proof = request.form.get("proof_text", "").strip()
    if len(proof) < 10:
        flash("Please provide a little more detail to help verify ownership.", "error")
    elif Claim.query.filter_by(match_id=match.id, claimant_id=current_user.id, status="pending").first():
        flash("You already have a pending claim for this match.", "error")
    else:
        db.session.add(Claim(match_id=match.id, claimant_id=current_user.id, proof_text=proof))
        db.session.commit()
        flash("Claim sent privately to the person who reported the found item.", "success")
    return redirect(url_for("matches_page"))


@app.route("/claims")
@login_required
def claims_page():
    claims = []
    for claim_obj in Claim.query.order_by(Claim.created_at.desc()).all():
        match = db.session.get(Match, claim_obj.match_id)
        if not match or not is_match_member(match):
            continue
        found = db.session.get(Item, match.found_id)
        if found and found.owner_id == current_user.id:
            claims.append((claim_obj, match, db.session.get(Item, match.lost_id)))
    return render_template("claims.html", claims=claims)


@app.route("/claim/<int:claim_id>/<decision>", methods=["POST"])
@login_required
def decide_claim(claim_id, decision):
    if decision not in {"approve", "reject"}:
        abort(404)
    claim_obj = db.session.get(Claim, claim_id)
    if not claim_obj:
        abort(404)
    match = db.session.get(Match, claim_obj.match_id)
    found = db.session.get(Item, match.found_id) if match else None
    if not found or found.owner_id != current_user.id:
        abort(403)
    if claim_obj.status != "pending":
        flash("This claim has already been reviewed.", "error")
    else:
        claim_obj.status = "approved" if decision == "approve" else "rejected"
        if decision == "approve":
            match.status = "claim-approved"
        db.session.commit()
        flash("Claim decision saved. Please arrange a safe handover in person.", "success")
    return redirect(url_for("claims_page"))


@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        abort(403)
    items = Item.query.order_by(Item.created_at.desc()).limit(200).all()
    claims = Claim.query.order_by(Claim.created_at.desc()).limit(200).all()
    users = User.query.order_by(User.id.desc()).limit(200).all()
    return render_template("admin.html", items=items, claims=claims, users=users)


@app.route("/admin/claim/<int:claim_id>/<decision>", methods=["POST"])
@login_required
def admin_decide_claim(claim_id, decision):
    if not current_user.is_admin:
        abort(403)
    if decision not in {"approve", "reject"}:
        abort(404)
    claim_obj = db.session.get(Claim, claim_id)
    if not claim_obj:
        abort(404)
    if claim_obj.status == "pending":
        claim_obj.status = "approved" if decision == "approve" else "rejected"
        match = db.session.get(Match, claim_obj.match_id)
        if match and decision == "approve":
            match.status = "claim-approved"
        db.session.commit()
        flash("Admin review saved. Arrange a safe handover; this is not proof of identity.", "success")
    else:
        flash("This claim has already been reviewed.", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/private-image/<int:item_id>")
@login_required
def private_image(item_id):
    item = db.session.get(Item, item_id)
    if not item:
        abort(404)
    allowed = item.owner_id == current_user.id
    if not allowed:
        related = Match.query.filter(
            ((Match.lost_id == item_id) | (Match.found_id == item_id))
        ).all()
        allowed = any(is_match_member(m) for m in related)
    if not allowed or not item.image_filename:
        abort(404)
    path = UPLOAD_DIR / item.image_filename
    if not path.exists():
        abort(404)
    return send_file(path)


@app.errorhandler(413)
def too_large(_error):
    return "Image too large. Maximum upload size is 5 MB.", 413


with app.app_context():
    (ROOT / "instance").mkdir(exist_ok=True)
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
