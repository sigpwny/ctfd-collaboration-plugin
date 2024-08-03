from __future__ import division  # Use floating point for math calculations

from flask import Blueprint, request
from flask import render_template as original_render_template

from CTFd.models import Challenges, Awards, db
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge
import CTFd.api.v1.challenges as challenges
from CTFd.plugins.migrations import upgrade
from CTFd.utils.user import get_current_user
from string import ascii_letters
import random, os
from functools import wraps
import datetime

class CollaborationChallengeModel(Challenges):
    __mapper_args__ = {
        'polymorphic_identity': 'collaboration',
    }
    def __init__(self, *args, **kwargs):
        super(CollaborationChallengeModel, self).__init__(*args, **kwargs)

class CollaborationChallenge(BaseChallenge):
    id = "collaboration"  # Unique identifier used to register challenges
    name = "collaboration"  # Name of a challenge type

    templates = {  # Handlebars templates used for each aspect of challenge editing & viewing
        "create": "/plugins/ctfd-collaboration-plugin/assets/create.html",
        "update": "/plugins/challenges/assets/update.html",
        "view": "/plugins/ctfd-collaboration-plugin/assets/view.html"
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        "create": "/plugins/challenges/assets/create.js",
        "update": "/plugins/challenges/assets/update.js",
        "view": "/plugins/challenges/assets/view.js"
    }
    # Route at which files are accessible. This must be registered using register_plugin_assets_directory()
    route = "/plugins/ctfd-collaboration-plugin/assets/"
    # Blueprint used to access the static_folder directory.
    blueprint = Blueprint(
        "ctfd-collaboration-plugin",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )
    challenge_model = CollaborationChallengeModel

    @classmethod
    def attempt(cls, challenge, request):

        data = request.form or request.get_json()
        submission = data["submission"].strip().split('.')
        if len(submission) != 3:
            return False, "Invalid collaboration token (not SECRET.X.Y)"

        secret, challenge_id, other_user_id = submission
        if challenge.id != int(challenge_id):
            return False, "That collaboration token is for a different challenge!"

        user = get_current_user()
        if user.id == int(other_user_id):
            return False, "You cannot submit your own collaboration token!"

        award_name = f'Collaboration between users {user.id} and {other_user_id} on {challenge_id}'

        matching_awards = Awards.query.filter(Awards.name == award_name).all()
        if len(matching_awards) > 0:
            return False, "You've already collaborated with this user on this challenge!"

        # Check if this is a valid secret
        random.seed(f'{other_user_id}-{challenge_id}-{os.getenv("SECRET_KEY")}')
        expected_secret = ''.join(random.choices(ascii_letters, k=8))
        if secret != expected_secret:
            return False, "Secret is incorrect (maybe a typo?)"

        award = Awards(user_id=user.id,
            team_id=user.team_id,
            name=award_name,
            value=challenge.value,
            icon="brain",
            date=datetime.datetime.now(datetime.UTC),
        )
        db.session.add(award)
        db.session.commit()

        # Don't 'solve' so that they can keep trying
        return False, "Successfully Awarded Points!"

def load(app):
    def get_challenge_decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if request.method != "GET":
                return f(*args, **kwargs)
            
            if kwargs.get("challenge_id") is None:
                return f(*args, **kwargs)
            
            challenge_id = kwargs["challenge_id"]

            user = get_current_user()
            if user is None:
                return f(*args, **kwargs)
        
            # Hook into render_template to provide a unique code we can render.
            random.seed(f'{user.id}-{challenge_id}-{os.getenv("SECRET_KEY")}')
            secret = ''.join(random.choices(ascii_letters, k=8))
            token = f'{secret}.{challenge_id}.{user.id}'

            def hooked_render_template(template, **kwargs):
                return original_render_template(template, token=token, **kwargs)
            
            challenges.render_template = hooked_render_template
            ret = f(*args, **kwargs)
            challenges.render_template = original_render_template
            return ret

        return wrapper

    upgrade(plugin_name="ctfd-collaboration-plugin")
    app.db.create_all()
    CHALLENGE_CLASSES["collaboration"] = CollaborationChallenge
    register_plugin_assets_directory(
        app, base_path="/plugins/ctfd-collaboration-plugin/assets/"
    )
    app.view_functions['api.challenges_challenge'] = get_challenge_decorator(app.view_functions['api.challenges_challenge'])