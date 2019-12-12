from flask import Flask, render_template, request, session, redirect, url_for, send_file
import os
import uuid
import hashlib
import pymysql.cursors
from functools import wraps
import time

app = Flask(__name__)
app.secret_key = "super secret key"
IMAGES_DIR = os.path.join(os.getcwd(), "images")

SALT = 'cs3083'

connection = pymysql.connect(host="localhost",
                             user="root",
                             password="",
                             db="finstagram",
                             charset="utf8mb4",
                             port=3306,
                             cursorclass=pymysql.cursors.DictCursor,
                             autocommit=True)

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if not "username" in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return dec

@app.route("/image/<image_name>", methods=["GET"])
def image(image_name):
    image_location = os.path.join(IMAGES_DIR, image_name)
    if os.path.isfile(image_location):
        return send_file(image_location, mimetype="image/jpg")
    
@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("home"))
    return render_template("index.html")

@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")

@app.route("/register", methods=["GET"])
def register():
    return render_template("register.html")

@app.route("/loginAuth", methods=["POST"])
def loginAuth():
    if request.form:
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"] + SALT
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()

        with connection.cursor() as cursor:
            query = "SELECT * FROM person WHERE username = %s AND password = %s"
            cursor.execute(query, (username, hashedPassword))
        data = cursor.fetchone()
        if data:
            session["username"] = username
            return redirect(url_for("home"))

        error = "Incorrect username or password."
        return render_template("login.html", error=error)

    error = "An unknown error has occurred. Please try again."
    return render_template("login.html", error=error)

@app.route("/registerAuth", methods=["POST"])
def registerAuth():
    if request.form:
        requestData = request.form
        firstName = requestData["fname"]
        lastName = requestData["lname"]
        username = requestData["username"]
        plaintextPasword = requestData["password"] + SALT
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()
        
        try:
            with connection.cursor() as cursor:
                query = "INSERT INTO person (username, password, firstName, lastName) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (username, hashedPassword, firstName, lastName))
        except pymysql.err.IntegrityError:
            error = "%s is already taken." % (username)
            return render_template('register.html', error=error)    

        return redirect(url_for("login"))

    error = "An error has occurred. Please try again."
    return render_template("register.html", error=error)

@app.route("/logout", methods=["GET"])
@login_required
def logout():
    session.pop("username")
    return redirect("/")

#Feature 1 & part of 2: Displays photos (photoID, photoPoster[name and ID], Time Stamp
@app.route("/home")
@login_required
def home():
    user = session['username']
    cursor = connection.cursor();
    query = '''SELECT DISTINCT photoID, filepath, photoPoster, firstName, lastName, postingdate
                FROM Photo JOIN Person ON photoPoster = username WHERE (allFollowers = True AND photoPoster IN
                (SELECT username_followed FROM Follow WHERE username_follower = %s AND followstatus = True)) OR
                (photoID IN (SELECT photoID FROM SharedWith WHERE (groupOwner, groupName) IN
                (SELECT groupOwner, groupName FROM BelongTo WHERE member_username = %s))) ORDER BY postingdate DESC'''
    cursor.execute(query, (user, user))
    data = cursor.fetchall()
    cursor.close()
    return render_template("home.html", username=user, posts=data)

#Feature 2 (d): Display Users who have been tagged and Accepted the tag
#ALSO Extra Feature: Feature 5 (a): Propose a Tag 
@app.route("/tags/<photo>", methods=["GET", "POST"])
@login_required
def tags(photo):
    user = session['username']
    photoID = photo
    cursor = connection.cursor();
    query = "SELECT * FROM Tagged NATURAL JOIN Person WHERE photoID = %s AND tagstatus = True"
    cursor.execute(query, photoID)
    data = cursor.fetchall()
    query = "SELECT * FROM Photo WHERE photoID = %s"
    cursor.execute(query, photoID)
    photo = cursor.fetchone()

    if request.form:
        requestData = request.form

        if "peer" in requestData:
            peer = '%' + requestData["peer"] + '%'
            query = "SELECT username, firstName, lastName FROM Person WHERE username LIKE %s"
            cursor.execute(query, peer)
            results = cursor.fetchall()
            cursor.close()
            if results:
                return render_template("tags.html", tags=data, photo=photo, results=results)

            error = "No users found, try again!"
            return render_template("tags.html", tags=data, photo=photo, msg=error)

        elif "NewTag" in requestData:
            peer = request.form["NewTag"]

            if user == peer:
                query = "INSERT INTO Tagged(username, photoID, tagstatus) VALUES (%s, %s, True)"
                msg = "You succesfully tagged yourself in this post!"

            else:
                query = '''SELECT * FROM Photo WHERE ((allFollowers = True AND photoPoster IN
                        (SELECT username_followed FROM Follow WHERE username_follower = %s AND followstatus = True))
                        OR (photoID IN (SELECT photoID FROM SharedWith WHERE (groupOwner, groupName) IN
                        (SELECT groupOwner, groupName FROM BelongTo WHERE member_username = %s)))) AND photoID = %s'''
                cursor.execute(query, (peer, peer, photoID))
                seen = cursor.fetchone()

                if seen:
                    query = "INSERT INTO Tagged(username, photoID, tagstatus) VALUES (%s, %s, FALSE)"
                    msg = "Tag Request sent to %s" % (peer)
                else:
                    error = "Cannot Process Tag Request"
                    return render_template("tags.html", tags=data, photo=photo, msg=error)
                    
            try:
                with connection.cursor() as cursor:
                    cursor.execute(query, (peer, photoID))
                    return render_template("tags.html", tags=data, photo=photo, msg=msg)
            except pymysql.err.IntegrityError:
                error = "A Tag Request already exists for %s." % (peer)
                return render_template("tags.html", tags=data, photo=photo, msg=error)

    return render_template("tags.html", tags=data, photo=photo)            

#Feature 2 (e): Display Username of people who hable liked the photo and the rating 
@app.route("/likes/<photo>", methods=["GET"])
@login_required
def likes(photo):
    photoID = photo
    cursor = connection.cursor();
    query = "SELECT * FROM Likes NATURAL JOIN Person WHERE photoID = %s"
    cursor.execute(query, photoID)
    data = cursor.fetchall()
    query = "SELECT * FROM Photo WHERE photoID = %s"
    cursor.execute(query, photoID)
    photo = cursor.fetchone()
    cursor.close()
    return render_template("likes.html", likes=data, photo=photo)

#Feature 3 Post a photo
@app.route("/upload", methods=["GET"])
@login_required
def upload():
    return render_template("upload.html")

#Feature 3 (a): Upload photo, sets up part b
@app.route("/uploadImage", methods=["POST"])
@login_required
def upload_image():
    user = session['username']
    if request.files:
        image_file = request.files.get("imageToUpload", "")
        image_name = image_file.filename
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)
        query = "INSERT INTO Photo(postingdate, filepath, photoPoster) VALUES (CURRENT_TIMESTAMP, %s, %s)"
        with connection.cursor() as cursor:
            cursor.execute(query, (image_name, user))
            postID = cursor.lastrowid
            query = "SELECT * FROM Photo WHERE photoID = %s"
            cursor.execute(query, postID)
            upload = cursor.fetchone()
            query = """SELECT F.groupName, F.groupOwner FROM BelongTo AS B JOIN Friendgroup AS F
                        ON B.groupName = F.groupName AND B.owner_username = F.groupOwner
                        WHERE B.member_username = %s """
            cursor.execute(query, user)
            groups = cursor.fetchall()
            cursor.close()
        return render_template("uploadDetails.html", photo=upload, friendGroups = groups)
    else:
        message = "Failed to upload image. Try Again!"
        return render_template("upload.html", message=message)

#Feature 3 (b): Handles allFollowers designation and sharing photo with FriendGroups
#Mini Extra feature = allosw user to enter caption
@app.route("/processDetails", methods=["POST"])
@login_required
def process_details():
    user = session['username']
    if request.form:
        cursor = connection.cursor();
        postID = request.form["post"]
        caption = request.form["caption"]
        query = "UPDATE Photo SET caption = %s WHERE photoID = %s"
        cursor.execute(query, (caption, postID))
        allFollowers = request.form["allFollowers"]
        query = "UPDATE Photo SET allFollowers = %s WHERE photoID = %s"
        cursor.execute(query, (allFollowers, postID))
        if request.form["groups"]:
            query = "INSERT INTO SharedWith(groupOwner, groupName, photoID) VALUES (%s, %s, %s)"
            sharedWith = request.form.getlist("groups")
            groups = [group.split('|') for group in sharedWith]
            for group in groups:
                cursor.execute(query, (group[1], group[0], postID))
        cursor.close()
    return redirect(url_for("home"))

#Feature 4 (a) part 1: User search - decided to implement with SQL LIKE operator. 
@app.route("/search", methods=["POST", "GET"])
@login_required
def search():
    if request.form:
        cursor = connection.cursor();
        requestData = request.form
        peer = '%' + requestData["peer"] + '%'
        query = "SELECT username, firstName, lastName FROM Person WHERE username LIKE %s"
        cursor.execute(query, peer)
        data = cursor.fetchall()
        cursor.close()
        if data:
            return render_template("search.html", users = data)

        error = "No users found, try again!"
        return render_template("search.html", msg=error)

    return render_template("search.html")

#Feature 4 (a) part 2: Handles the Follow Request after search 
@app.route("/follow", methods=["POST"])
@login_required
def follow():
    user = session['username']
    if request.form:
        peer = request.form["follow"]
        
        try:
            with connection.cursor() as cursor:
                query = "INSERT INTO Follow (username_followed, username_follower, followstatus) VALUES (%s, %s, FALSE)"
                cursor.execute(query, (peer, user))
        except pymysql.err.IntegrityError:
            error = "You already sent a folow request to %s." % (peer)
            return render_template('search.html', msg=error)

        msg = "Follow Request sent to %s" % (peer)
        return render_template('search.html', msg=msg)

#Feature 4 (b) part 1: Displays pending Follow Requests of the user
@app.route("/followRequests")
@login_required
def followRequests():
    user = session['username']
    cursor = connection.cursor();
    query = '''SELECT username_follower, firstName, lastName
                FROM Follow JOIN Person ON username_follower = username
                WHERE (username_followed = %s ) AND (followstatus = False)'''
    cursor.execute(query, user)
    data = cursor.fetchall()
    return render_template("followRequests.html", requests=data)

#Feature 4 (b) part 2: Handles the answer for the Pending Follow Requests i.e Accept or Decline
@app.route("/handleRequest", methods=["POST"])
@login_required
def handleRequest():
    user = session['username']
    cursor = connection.cursor();
    
    if "Accept" in request.form:
        peer = request.form.get('Accept')
        query = "UPDATE Follow SET followstatus = TRUE WHERE (username_followed = %s) AND (username_follower = %s)"
        cursor.execute(query, (user, peer))
    
    elif "Decline" in request.form:
        peer = request.form.get('Decline')
        query = "DELETE FROM Follow WHERE (username_followed = %s) AND (username_follower = %s)"
        cursor.execute(query, (user, peer))

    cursor.close()
    return redirect(url_for('followRequests'))

#Extra Feature - Feature 5 (b): Show Pending Tag Requests
@app.route("/showTags")
@login_required
def showTags():
    user = session['username']
    cursor = connection.cursor();
    query = 'SELECT * FROM Tagged NATURAL JOIN Photo WHERE username = %s AND tagstatus = False'
    cursor.execute(query, user)
    tags = cursor.fetchall()
    cursor.close()
    return render_template("showTags.html", requests = tags)

#Extra Feature - Feature 5 (b): Accept/Decline Tag Requests 
@app.route("/manageTags", methods=["POST"])
@login_required
def manageTags():
    user = session['username']
    cursor = connection.cursor();
    
    if "Accept" in request.form:
        post = request.form.get('Accept')
        query = "UPDATE Tagged SET tagstatus = TRUE WHERE username = %s and photoID = %s"
        cursor.execute(query, (user, post))
    
    elif "Decline" in request.form:
        post = request.form.get('Decline')
        query = "DELETE FROM Tagged WHERE (username = %s) AND (photoID = %s)"
        cursor.execute(query, (user, post))

    cursor.close()
    return redirect(url_for('showTags'))
        


if __name__ == "__main__":
    if not os.path.isdir("images"):
        os.mkdir(IMAGES_DIR)
    app.run()

