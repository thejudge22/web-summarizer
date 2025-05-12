# ABOUTME: Handles authentication logic, login_required decorator, and session management.
# ABOUTME: Used to protect routes and manage user sessions.

import functools
from flask import session, redirect, url_for, flash, request
from config import Config

def login_required(view):
    """View decorator that redirects anonymous users to the login page."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'logged_in' not in session:
            flash("Please log in to access this page.", "info")
            # Store the requested URL in the session to redirect after login
            next_url = request.url
            return redirect(url_for('login', next=next_url))
        return view(**kwargs)
    return wrapped_view