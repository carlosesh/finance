import os
import requests

from cs50 import SQL
from datetime import datetime
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash


from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# set API Key variable
API_KEY = os.environ.get("API_KEY")

# Make sure API key is set
if not API_KEY:
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    shares = db.execute("SELECT symbol, shares, name, price, total FROM shares join users on id = user_id where id = ? and shares > 0;", session["user_id"])

    currentCash = db.execute("SELECT cash FROM users where id = ?;", session["user_id"])

    stocksTotalQuery = db.execute("SELECT sum(total) as total FROM shares join users on id = user_id where id = ? and shares > 0;", session["user_id"])

    stocksTotal = stocksTotalQuery[0]["total"];

    return render_template("index.html", shares = shares, currentCash = currentCash, stocksTotal = 0 if stocksTotal is None else stocksTotal)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # get the symbol and values from the form
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        if not symbol:
            return apology("You must provide a symbol", 400)

        if not shares:
            return apology("You must provide the number of shares greater than 0", 400)

        try:
            # make a request to fetch the most up to date
            req = requests.get(f'https://cloud.iexapis.com/stable/stock/{symbol}/quote?token={API_KEY}&filter=symbol,companyName,latestPrice').json()

            # get the current price of the share
            price = req["latestPrice"]

            # get the company name
            companyName = req["companyName"]

            # get the current date and time
            dateTimeNow = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Query database for user cash
            row = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

            # set the cash variable
            cash = row[0]["cash"]

            # calculate the shares * price value
            sharesTimesPrice = shares*price

            if sharesTimesPrice > cash:
                return apology("CAN'T AFFORD", 400)

            # query for the stocks you already own
            stocks = db.execute("select name, shares from shares where user_id = ? and symbol = ?;", session["user_id"], symbol)

            # check if oyu already have that stock, if returns 1 then you already have it and you increment the number of shares
            if len(stocks) == 1 and stocks[0]['shares'] > 0:
                # update the existing stocks
                newShares = stocks[0]["shares"] + shares
                db.execute("UPDATE shares SET shares = ?, total = ? WHERE user_id = ?", newShares, newShares*price, session["user_id"])

                #update the history table
                db.execute("INSERT INTO history (user_id, symbol, shares, price, date_tm) VALUES(?, ?, ?, ?, ?)",
                            session["user_id"], symbol, shares, price, dateTimeNow)

            # you don't have any stocks for that symbol, add it to the db
            else:
                # execute insert statement to shares table
                db.execute("INSERT INTO shares (user_id, name, symbol, shares, price, total, date_tm) VALUES(?, ?, ?, ?, ?, ?, ?)",
                            session["user_id"], companyName, symbol, shares, price, sharesTimesPrice, dateTimeNow)

                #update the history table
                db.execute("INSERT INTO history (user_id, symbol, shares, price, date_tm) VALUES(?, ?, ?, ?, ?)",
                            session["user_id"], symbol, shares, price, dateTimeNow)

            # update the amount of cash the user has after the purchase
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash-sharesTimesPrice, session["user_id"])

            return redirect("/")
        except:
            return apology("Invalid symbol, try a different one or amount of shares", 403)

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query database for transactions history
    rows = db.execute("SELECT * FROM history WHERE user_id = ? and shares <> 0;", session["user_id"])

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        symbol = request.form.get("symbol")

        try:
          req = requests.get(f'https://cloud.iexapis.com/stable/stock/{symbol}/quote?token={API_KEY}&filter=symbol,companyName,latestPrice').json()
        except:
          return apology("Invalid symbol, try a different one", 403)

        return render_template("quotePrice.html", req=req)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

     # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        passwordAgain = request.form.get("passwordAgain")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 403)

        # Ensure passwordAgain was submitted
        elif not passwordAgain:
            return apology("must provide password the same password in this field", 403)

        # Ensure password and passwordAgain are equal
        elif password != passwordAgain:
            return apology("passwords must match", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          username)

        # check for existing user
        if len(rows) == 1:
            return apology("Username Already exist", 403)
        else:
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
            username, generate_password_hash(password))

        # Redirect user to home page
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # get the symbol and amount of shares from the fom
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        # make a request to fetch the most up to date price
        req = requests.get(f'https://cloud.iexapis.com/stable/stock/{symbol}/quote?token={API_KEY}&filter=latestPrice').json()

        # set the price variable to the value from the request
        price = req["latestPrice"]

        # query for the current cash
        currentCash = db.execute("SELECT cash FROM users where id = ?;", session["user_id"])

        newCash = (shares*price)+currentCash[0]["cash"]

        # query for the current shares
        currentShares = db.execute("select shares from shares where user_id = ? and symbol = ?", session["user_id"], symbol)

        if(shares > currentShares[0]['shares']):
            return apology("Trying to sell more shares than what you have, huh?", 400)

        # update the number of available shares to the user
        db.execute("UPDATE shares SET shares = ? where user_id = ? and symbol = ?;", currentShares[0]['shares']-shares, session["user_id"], symbol)

        # update the new cash value from having sold N amount of shares
        db.execute("UPDATE users SET cash = ? where id = ?;", newCash, session["user_id"])

        currentShares = db.execute("select shares from shares where user_id = ? and symbol = ?", session["user_id"], symbol)

        # update the total you own of the share
        db.execute("UPDATE shares SET total = ? where user_id = ? and symbol = ?;", currentShares[0]['shares']*price, session["user_id"], symbol)

        # get the current date and time
        dateTimeNow = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        #update the history table
        db.execute("INSERT INTO history (user_id, symbol, shares, price, date_tm) VALUES(?, ?, ?, ?, ?)",
                    session["user_id"], symbol, (-1*shares), price, dateTimeNow)

        return redirect("/")
    else:
        # Query database for symbols
        symbols = db.execute("SELECT symbol FROM shares WHERE user_id = ? and shares > 0;", session["user_id"])

        return render_template("sell.html", symbols = symbols)

@app.route("/funds", methods=["GET", "POST"])
@login_required
def funds():
    """Add more funds to your account"""

    cash = db.execute("SELECT cash FROM users where id = ?;", session["user_id"])
    currentCash = cash[0]['cash']

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # get the currentFunds and newFunds from the form
        newFunds = int(request.form.get("newFunds"))

        # update the amount of cash the user has after the purchase
        db.execute("UPDATE users SET cash = ? WHERE id = ?", currentCash+newFunds, session["user_id"])

        return redirect("/")
    else:

        return render_template("funds.html", currentCash = currentCash)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
