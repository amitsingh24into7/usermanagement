# Home.py
import streamlit as st
from db.connection import get_db_connection, hash_password
from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime, timedelta

# Load environment (for local dev)
load_dotenv()

# -------------------------------
# 🔐 Admin Login with Session Persistence
# -------------------------------
def admin_login():
    st.title("🔐 User Master Admin")
    st.subheader("Centralized User Management")

    # Check if already logged in via token
    if "admin_logged_in" in st.session_state and st.session_state.admin_logged_in:
        return True

    # Show login form
    email = st.text_input("Admin Email")
    password = st.text_input("Password", type="password")

    if st.button("Login as Admin"):
        ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
        ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

        if not ADMIN_EMAIL or not ADMIN_PASSWORD:
            st.error("❌ Admin credentials not set in environment.")
            return False

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            st.session_state.admin_logged_in = True
            st.session_state.admin_email = email
            # Add auth token to URL
            st.query_params["auth"] = "admin"  # simple token
            st.rerun()
        else:
            st.error("❌ Invalid admin credentials")

    return False

# Check login status
auth_token = st.query_params.get("auth")
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

if not st.session_state.admin_logged_in:
    if auth_token == "admin":
        st.session_state.admin_logged_in = True
    else:
        admin_login()
        st.stop()

# -------------------------------
# 🎯 Main Admin Dashboard
# -------------------------------
st.set_page_config(page_title="User Master Admin", layout="wide")
st.title("🔐 User Master Admin")
st.markdown("Manage users across all applications")

if st.button("🚪 Logout", key="admin_logout"):
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

# -------------------------------
# 📚 Fetch App URLs from DB
# -------------------------------
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_app_urls():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT slug, name, login_url FROM apps")
                rows = cur.fetchall()
        return {row[0]: {"name": row[1], "login_url": row[2]} for row in rows}
    except Exception as e:
        st.warning(f"⚠️ Could not load app URLs: {e}")
        return {}

app_urls = get_app_urls()

# -------------------------------
# 📋 Fetch Users from DB
# -------------------------------
@st.cache_data(ttl=60)
def load_users():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, username, mobile, valid_until, is_active, app_slug
                    FROM users
                    ORDER BY app_slug, valid_until
                """)
                rows = cur.fetchall()
        return [
            dict(zip(["id", "username", "mobile", "valid_until", "is_active", "app_slug"], row))
            for row in rows
        ]
    except Exception as e:
        st.error("❌ Failed to load users from database.")
        st.exception(e)
        return []

users = load_users()

if not users:
    st.info("📭 No users found. Add your first user below.")
else:
    # Group by app_slug
    apps = {}
    for user in users:
        app = user["app_slug"]
        if app not in apps:
            apps[app] = []
        apps[app].append(user)

    # Display users by app (collapsed by default)
    st.markdown("### 📂 Users by Application")

    for app_slug, user_list in apps.items():
        app_info = app_urls.get(app_slug, {"name": app_slug, "login_url": "https://example.com"})
        app_name = app_info["name"]

        with st.expander(f"📦 {app_name} ({len(user_list)} users)", expanded=False):  # ← Now collapsed
            df = pd.DataFrame(user_list)
            df["valid_until"] = pd.to_datetime(df["valid_until"])
            df["Days Left"] = (df["valid_until"] - pd.Timestamp.today()).dt.days
            df["Status"] = df["is_active"].map({True: "✅ Active", False: "🔴 Inactive"})
            st.dataframe(
                df[["username", "mobile", "valid_until", "Days Left", "Status"]],
                use_container_width=True
            )

            # Edit User Button - shown next to each email
            for user in user_list:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**📧 {user['username']}**<br><small>📱 {user['mobile']}</small>", unsafe_allow_html=True)
                with col2:
                    if st.button("✏️ Edit", key=f"edit_{user['id']}"):
                        st.session_state.edit_user = user

# -------------------------------
# ✏️ Edit User Modal
# -------------------------------
if "edit_user" in st.session_state:
    user = st.session_state.edit_user
    app_info = app_urls.get(user["app_slug"], {"name": user["app_slug"], "login_url": "https://example.com"})
    st.divider()
    st.subheader("✏️ Edit User")

    with st.form("edit_user_form"):
        new_mobile = st.text_input("📱 Mobile", value=user["mobile"])
        new_validity = st.date_input("📅 New Valid Until", value=user["valid_until"])
        is_active = st.checkbox("✅ Active", value=user["is_active"])
        update_btn = st.form_submit_button("💾 Update User")

    if update_btn:
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users
                        SET mobile = %s, valid_until = %s, is_active = %s
                        WHERE id = %s
                    """, (new_mobile, new_validity, is_active, user["id"]))
                conn.commit()
            st.success("✅ User updated successfully!")
            st.session_state.pop("edit_user")
            st.cache_data.clear()  # Refresh user list
            st.rerun()
        except Exception as e:
            st.error(f"❌ Database error: {e}")

# -------------------------------
# ➕ Add New User
# -------------------------------
st.markdown("---")
st.subheader("➕ Add New User")

with st.form("add_user_form"):
    username = st.text_input("📧 Email (Username)")
    mobile = st.text_input("📱 Mobile (with country code, e.g. +919876543210)")
    
    # Dynamically load app slugs
    available_apps = list(app_urls.keys()) if app_urls else ["nism-test", "lawdict", "stockai"]
    app_slug = st.selectbox("📋 Application", available_apps)
    
    validity_days = st.selectbox("⏳ Validity", [30, 60, 90, 180, 365])
    password = st.text_input("🔑 Set Password", type="password", value="welcome123")
    
    submitted = st.form_submit_button("Add User & Generate WhatsApp")

if submitted:
    if not username or not mobile:
        st.error("❌ All fields are required.")
    elif "@" not in username:
        st.error("❌ Invalid email address.")
    elif app_slug not in app_urls:
        st.error("❌ Invalid application selected.")
    else:
        valid_until = (datetime.now() + timedelta(days=validity_days)).date()
        hashed_pw = hash_password(password)
        login_url = app_urls[app_slug]["login_url"]

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (username, mobile, password_hash, valid_until, app_slug)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (app_slug, username) DO UPDATE
                        SET password_hash = EXCLUDED.password_hash,
                            valid_until = EXCLUDED.valid_until,
                            is_active = TRUE
                    """, (username, mobile, hashed_pw, valid_until, app_slug))
                conn.commit()

            # Generate WhatsApp message
            message = (
                f"🎉 Welcome to {app_urls[app_slug]['name']}!\n\n"
                f"📧 *Username:* {username}\n"
                f"🔐 *Password:* {password}\n"
                f"📅 *Valid Until:* {valid_until}\n\n"
                f"🔗 Login: {login_url}\n\n"
                f"Best of luck! 🚀"
            )
            whatsapp_link = f"https://wa.me/{mobile.replace('+', '')}?text={message.replace(' ', '%20').replace('\n', '%0A')}"

            st.success("✅ User added successfully!")
            st.markdown(f"<a href='{whatsapp_link}' target='_blank' style='font-size:18px;'>📤 Send WhatsApp Message</a>", unsafe_allow_html=True)
            st.balloons()

            # Clear cache to show updated list
            st.cache_data.clear()

        except Exception as e:
            st.error(f"❌ Database error: {e}")