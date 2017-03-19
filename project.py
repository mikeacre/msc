from flask import Flask, render_template, request
from flask import redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from db_setup import Base, Category, User, OddItem
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests
import os
from werkzeug.utils import secure_filename
import smtplib
from functools import wraps
from PIL import Image



# Folder where imaages will be uploaded
UPLOAD_FOLDER = './static/itempics'
# Extensions for images that may be uploaded
ALLOWED_EXTENSIONS = set(['jpg', 'jpeg', 'gif', 'png'])
app = Flask(__name__, static_url_path='/static')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.debug = True
TEMPLATES_AUTO_RELOAD = True
CLIENT_ID = json.loads(
    open('/var/www/msc/client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Odd Item Application"

# Connect to Database and create database session
engine = create_engine('sqlite:////var/www/msc/odddb.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in login_session:
            flash('Please log-in to access that page.')
            return redirect(url_for('showLogin'))
        return f(*args, **kwargs)
    return decorated_function


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data

    app_id = json.loads(open('fb_client_secrets.json').read())['web']['app_id']
    app_secret = json.loads(open(
        'fb_client_secrets.json').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (
        app_id, app_secret, access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    userinfo_url = "https://graph.facebook.com/v2.4/me"
    token = result.split("&")[0]

    url = 'https://graph.facebook.com/v2.4/me?%s&fields=name,id,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)
    login_session['name'] = data['name']
    login_session['email'] = data['email']
    login_session['facebook_id'] = data['id']
    login_session['access_token'] = token
    login_session['provider'] = 'facebook'

    url = 'https://graph.facebook.com/v2.4/me/picture?%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['name']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: "'
    output += '150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;">'
    flash("you are now logged in as %s" % login_session['name'])
    print "done!"
    return output


@app.route('/disconnect')
def disconnect():

    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            del login_session['gplus_id']
        if login_session['provider'] == 'facebook':
            fbdisconnect()
            del login_session['facebook_id']
        del login_session['access_token']
        del login_session['email']
        del login_session['name']
        del login_session['picture']
        del login_session['user_id']
        del login_session['provider']
        flash("You have successfully been logged out.")
        return redirect(url_for('home'))
    else:
        flash("You were not logged in")
        return redirect(url_for('home'))


@app.route('/fbdisconnect')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?access_token=%s' % (
        facebook_id, access_token)
    h = httplib2.Http()
    result = h.request(url, 'DELETE')[1]
    return "you have been logged out"


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(
            json.dumps('Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id
    login_session['provider'] = 'google'

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['name'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id
    output = ''
    output += '<h1>Welcome, '
    output += login_session['name']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: "'
    output += '150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;">'
    flash("you are now logged in as %s" % login_session['name'])
    print "done!"
    return output


def createUser(login_session):
    newUser = User(name=login_session['name'],
                   email=login_session['email'],
                   picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


@app.route('/gdisconnect')
def gdisconnect():
    if 'user_id' not in login_session:
        return redirect('/login')
    access_token = login_session['access_token']
    print 'In gdisconnect access token is %s', access_token
    print 'User name is: '
    print login_session['name']
    if access_token is None:
        print 'Access Token is None'
        response = make_response(json.dumps('Current user not connected.'),
            401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    if result['status'] == '200':
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/myaccount/', methods=['GET', 'POST'])
@login_required
def myAccount():
    if request.method == 'POST':
        return render_template('addcategory.html')
    else:
        return render_template('myaccount.html')


@app.route('/addcategory/', methods=['GET', 'POST'])
@login_required
def addCategory():
    if request.method == 'POST':
        newCategory = Category(
            name=request.form['name'],
            description=request.form['description'])
        session.add(newCategory)
        session.flush()
        if 'file' not in request.files:
            photo = 'default.jpg'
        else:
            file = request.files['file']
            extension = file.filename.rsplit('.', 1)[1].lower()
            photo = "category%s.%s" % (newCategory.id, extension)
            file.filename = photo
            # if user does not select file, browser also
            # submit a empty part without filename
            if file.filename == '':
                filename = 'default.jpg'
            if file and allowed_file(file.filename):
                uploadImage(file, os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename)))

        flash('New category %s Successfully Created' % newCategory.name)
        newCategory.picture = photo
        session.commit()

        return redirect(url_for('home'))
    else:
        return render_template('addcategory.html')


@app.route('/deleteitem/<int:item_id>/<int:confirm_id>/')
@login_required
def deleteItemConfirm(item_id, confirm_id):
    item = session.query(OddItem).filter_by(id=item_id).one()
    if item.user.id == login_session['user_id']:
        os.remove("%s/%s" % (UPLOAD_FOLDER,item.picture))
        session.delete(item)
        flash('Item Deleted')
        session.commit()
        return redirect(url_for('home'))


@app.route('/deleteitem/<int:item_id>/')
@login_required
def deleteItem(item_id):
    item = session.query(OddItem).filter_by(id=item_id).one()
    return render_template('confirmdelete.html', item=item)


@app.route('/deletecategory/<int:category_id>/<int:confirm_id>/')
@login_required
def deleteCategoryConfirm(category_id, confirm_id):
    if 'name' not in login_session and login_session['name'] != 'Mike Acre':
        return redirect(url_for('home'))
    category = session.query(Category).filter_by(id=category_id).one()
    session.delete(category)
    flash('Category Deleted')
    session.commit()
    return redirect(url_for('home'))


@app.route('/deletecategory/<int:category_id>/')
@login_required
def deleteCategory(category_id):
    if 'name' not in login_session and login_session['name'] != 'Mike Acre':
        return redirect(url_for('home'))
    category = session.query(Category).filter_by(id=category_id).one()
    return render_template('confirmdeletecategory.html', category=category)


@app.route('/edititem/<int:item_id>/', methods=['GET', 'POST'])
@login_required
def editItem(item_id):
    item = session.query(OddItem).filter_by(id=item_id).one()
    if item.user.id != login_session['user_id']:
        flash('That is not your item!')
        return redirect(url_for('home'))
    if request.method == 'POST':
        item.title = request.form['title']
        item.description = request.form['description']
        item.price = request.form['price']
        return redirect(url_for('displayItem', item_id=item_id))
    else:
        categories = session.query(Category).all()
        return render_template('edititem.html',
                               item=item,
                               categories=categories)


@app.route('/additem/<int:category_id>/', methods=['GET', 'POST'])
@login_required
def addItem(category_id):
    if request.method == 'POST':
        newItem = OddItem(
                          title=request.form['name'],
                          description=request.form['description'],
                          price=request.form['price'],
                          category_id=request.form['category'],
                          user_id=login_session['user_id'])
        session.add(newItem)
        session.flush()
        if request.files['file'].filename == '':
            photo = 'default.jpg'
        else:
            file = request.files['file']
            extension = file.filename.rsplit('.', 1)[1].lower()
            photo = "%s.%s" % (newItem.id, extension)
            file.filename = photo
            # if user does not select file, browser also
            # submit a empty part without filename
            if file.filename == '':
                file.filename = 'default.jpg'
            if file and allowed_file(file.filename):
                uploadImage(file, os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename)))


        newItem.picture = photo
        flash('New item %s Successfully Created' % photo)
        session.commit()
        return redirect(url_for('items', category_id=newItem.category_id))
    else:
        categories = session.query(Category).all()
        thiscategory = session.query(Category).filter_by(id=category_id).one()
        return render_template('additem.html',
                               categories=categories,
                               thiscategory=thiscategory)


def uploadImage(file, filename):
    maxsize = (1028, 1028)
    img = Image.open(file)
    img.thumbnail(maxsize, Image.ANTIALIAS)
    img.save(filename)


@app.route('/items/<int:category_id>/')
def items(category_id):
    items = session.query(OddItem).filter_by(
        category_id=category_id).order_by("id desc").all()
    category = session.query(Category).filter_by(
        id=category_id).one()
    if 'name' in login_session and login_session['name'] == 'Mike Acre':
        return render_template('items.html',
                               items=items,
                               category=category,
                               admin='yes')
    else:
        return render_template('items.html',
                               items=items,
                               category=category,
                               admin='no')


@app.route('/displayItem/<int:item_id>/', methods=['GET'])
def displayItem(item_id):
    item = session.query(OddItem).filter_by(
        id=item_id).one()
    return render_template('item.html', item=item)


@app.route('/showuser/<int:user_id>', methods=['GET', 'POST'])
def showUser(user_id):
    user = session.query(User).filter_by(
        id=user_id).one()
    items = session.query(OddItem).filter_by(
        user_id=user_id).all()
    return render_template('user.html', user=user, items=items)


@app.route('/showusers/', methods=['GET'])
def showUsers():
    users = session.query(User).all()
    return render_template('showusers.html', users=users)


@app.route('/')
def home():
    categories = session.query(Category).order_by("name asc").all()
    return render_template('categories.html', categories=categories)


# JSON response for all Categories
@app.route('/categories/JSON')
def categoriesJSON():
    categories = session.query(Category).all()
    return jsonify(Category=[c.serialize for c in categories])


# JSON for Items by Category
@app.route('/items/category/<int:category_id>/JSON')
def itemsByCategoryJSON(category_id):
    items = session.query(OddItem).filter_by(category_id=category_id).all()
    return jsonify(Category=[i.serialize for i in items])

# Json for Items by user
@app.route('/items/user/<int:user_id>/JSON')
def itemsByUserJSON(user_id):
    items = session.query(OddItem).filter_by(user_id=user_id).all()
    return jsonify(Category=[i.serialize for i in items])

# Json for Items by user
@app.route('/item/<int:item_id>/JSON')
def itemJSON(item_id):
    item = session.query(OddItem).filter_by(id=item_id).one()
    return jsonify(Category=[item.serialize])

if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.run()
