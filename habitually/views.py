from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .models import User, Category, Habit, Completion

import random

import datetime

import json

DAYS_PER_WEEK = 7

# Create your views here.

def index(request):
    # Check if user is logged in
    if request.user.is_authenticated:
        categories = Category.objects.all()
        column_keys = list(reversed(range(0, 7)))
        user_habits = request.user.habits.all()

        # Create a list of the user's habits
        user_habits_list = request.user.habits.all().values_list("name", flat=True)

        # Create a list of admin-created habits
        admin_habits = Habit.objects.filter(creator__in=[1, 2]).values_list("name", flat=True)

        # Create a list of admin-created habits that are not in the user's list of habits
        not_user_habits = []
        for habit in admin_habits:
            if habit not in user_habits_list:
                not_user_habits.append(habit)

        # Create a list of 5 random habits to suggest to the user
        random.shuffle(not_user_habits)
        suggested_habits = not_user_habits[0:5]

        return render(request, "habitually/index.html", {
            "categories": categories,
            "column_keys": column_keys,
            "user_habits": user_habits,
            "suggested_habits": suggested_habits
        })
    else:
        return render(request, "habitually/index.html")


def login_view(request):
    if request.method == "POST":
        # Attempt to sign user in
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        # Check if authentication successful
        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("index"))
        else:
            return render(request, "habitually/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "habitually/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]

        # Ensure password matches confirmation
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        if password != confirmation:
            return render(request, "habitually/register.html", {
                "message": "Passwords must match."
            })

        # Attempt to create new user
        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "habitually/register.html", {
                "message": "Username already taken."
            })
        login(request, user)
        return HttpResponseRedirect(reverse("index"))
    else:
        return render(request, "habitually/register.html")


# Add a new habit
@login_required
def add_habit(request):
    # Check if method is POST
    if request.method == "POST":
        # Display error message if user has previously added the habit
        user_habits = request.user.habits.all()
        for user_habit in user_habits:
            if request.POST["habit"].casefold() == user_habit.name.casefold():
                return render(request, "habitually/index.html", {
                    "categories": Category.objects.all(),
                    "user_habits": user_habits,
                    # TODO: Add suggested habits to this list, and refactor process from index?
                    "day_keys": list(reversed(range(0, 7))),
                    "message": "ERROR: You've already added this habit!"
                })

        # Store data in Habit model fields and save
        habit = Habit()
        habit.creator = request.user
        habit.name = request.POST["habit"]
        habit.category = Category.objects.get(category=request.POST["category"])
        habit.save()
    return HttpResponseRedirect(reverse("index"))


# Add suggested habits
@login_required
def add_suggested_habits(request):
    # Check if method is POST
    if request.method == "POST":
        # Get list of habits checked by the user
        habits = request.POST.getlist("habit")
        for habit in habits:
            # Get the category of the habit
            original_habit_obj = Habit.objects.get(name=habit, creator__in=[1, 2])
            category = original_habit_obj.category

            # Create a new habit for the user
            new_habit = Habit()
            new_habit.creator = request.user
            new_habit.name = habit
            new_habit.category = category
            new_habit.save()
    return HttpResponseRedirect(reverse("index"))


# Delete an existing habit
@login_required
def delete_habit(request, doer, habit_id):
    # Confirm that doer is current user
    if request.user.username == doer:
        try:
            habit = Habit.objects.get(pk=habit_id, creator=request.user)
            habit.delete()
            return JsonResponse({"message": "Habit deleted successfully."})
        except Habit.DoesNotExist:
            return JsonResponse({"error": "Habit not found."}, status=404)
    else:
        return JsonResponse({"error": "An error occurred."}, status=404)


# Get or toggle habit completion status
@login_required
def habit_completion_status(request, doer, habit_id, date, action):
    # Confirm that doer is current user
    if request.user.username == doer:
        try:
            # Check if Completion object for that habit, doer, and date already exists
            completion = Completion.objects.get(habit=habit_id, doer=request.user, time=date)

            # Check user's requested action
            if action == "get_status":
                return JsonResponse({"status": completion.status})
            elif action == "toggle_status":
                # Change status to opposite of current status
                completion.status = not completion.status
                completion.save()
        except Completion.DoesNotExist:

            # Check user's requested action
            if action == "get_status":
                return JsonResponse({"status": False})
            elif action == "toggle_status":
                # Create a new completion object and set status to True
                completion = Completion()
                completion.doer = request.user
                completion.habit = Habit.objects.get(pk=habit_id, creator=request.user)
                completion.time = date
                completion.status = True
                completion.save()
        return JsonResponse({"habit_id": habit_id, "date": completion.time, "status": completion.status})
    else:
        return JsonResponse({"error": "An error occurred."}, status=404)



@login_required
def overall_habit_completion_rate(request):
    completion_rates = []
    user_habits = request.user.habits.all()

    for i in range(6, -1, -1):
        date = get_date_i_days_ago(i)

        habits_completed_on_date = 0
        for habit in user_habits:
            try:
                completion = Completion.objects.get(habit=habit.id, doer=request.user, time=date)
                if completion.status:
                    habits_completed_on_date += 1
            except Completion.DoesNotExist:
                pass

        completion_rate = round(habits_completed_on_date / len(user_habits) * 100, 1)
        completion_rates.append(completion_rate)
    return JsonResponse(completion_rates, safe=False)

def get_date_i_days_ago(i):
    date = datetime.date.today() - datetime.timedelta(days=i)
    return date

@login_required
def seven_day_habit_completion_rates(request):
    # Get the IDs of the user's habits
    user_habits = request.user.habits.all()

    seven_day_completion_rates = {}
    for habit in user_habits:
        times_completed_this_week = 0
        for i in range(0, 7):
            date = get_date_i_days_ago(i)

            # Get completion status of this habit for the day
            try:
                completion = Completion.objects.get(habit=habit.id, doer=request.user, time=date)
                if completion.status:
                    times_completed_this_week += 1
            except:
                pass
        seven_day_completion_rates[habit.name] = round(times_completed_this_week / DAYS_PER_WEEK * 100, 1 )

        sorted_dict = {}
        sorted_values = sorted(seven_day_completion_rates.values(), reverse=True)
        for value in sorted_values:
            for key in seven_day_completion_rates.keys():
                if seven_day_completion_rates[key] == value:
                    sorted_dict[key] = seven_day_completion_rates[key]
    return JsonResponse(sorted_dict)

# Get date after date in focus for range (second argument in Python range is not included)
        # date_plus_one_day = date + datetime.timedelta(days=1)
        #habits_on_date = request.user.habits.filter(creation_time__range=["2021-11-15", date_plus_one_day]).values_list("id", flat=True)
        #habit_count_on_date = len(habits_on_date)
from itertools import groupby

@login_required
def completion_streaks_per_habit(request, streak):
    user_habits = request.user.habits.all()

    # Get current date and day after for date range
    current_date = datetime.date.today()
    current_date_plus_one_day = current_date + datetime.timedelta(days=1)

    # Create a dict to store each habit's streaks
    streaks_dict = {}
    for habit in user_habits:

        # Get a sorted list of all dates with completion data and their completion statuses (True/False)
        full_completion_data = sorted(list(Completion.objects.filter(habit=habit.id, doer=request.user, time__range=["2000-01-01", current_date_plus_one_day]).values_list("time", "status")))

        habit_streak = 0

        # Check if there is completion data
        if len(full_completion_data) != 0:

            # Create a list with only dates (converted to ordinals) that have True completion statuses
            completion_dates_true = []
            for i in range(len(full_completion_data)):
                if full_completion_data[i][1] is True:
                    completion_dates_true.append(full_completion_data[i][0].toordinal())

            # Check if there are any dates with True completion statuses
            if len(completion_dates_true) != 0:
                # Check if longest streak was requested
                if streak == "longest":
                    # Set longest and current streak variables to 1
                    longest_streak = 1
                    current_longest_streak = 1

                    # For each date with a True completion status
                    for i in range(len(completion_dates_true) - 1):
                        # Check if the next date in the list is a consecutive date
                        if completion_dates_true[i] + 1 == completion_dates_true[i + 1]:
                            # Add to current streak
                            current_longest_streak += 1
                            # Set longest streak's value to current streak's value
                            if current_longest_streak > longest_streak:
                                longest_streak = current_longest_streak
                        else:
                            # Reset current streak to 1
                            current_longest_streak = 1
                    habit_streak = longest_streak
                # Check if current streak was requested
                elif streak =="current":
                    if completion_dates_true[-1] != current_date.toordinal():
                        habit_streak = 0
                    else:
                        habit_streak = 1
                        for i in range(len(completion_dates_true) - 1, 0, -1):
                            if completion_dates_true[i] - 1 == completion_dates_true[i - 1]:
                                habit_streak += 1
                            else:
                                break
            else:
                # Set longest streak to 0
                habit_streak = 0
        else:
            # Set longest streak to 0
            habit_streak = 0

        # Add habit name and longest streak data to the streaks dict
        streaks_dict[habit.id] = habit_streak
    return JsonResponse(streaks_dict)

@login_required
def get_habit_count(request):
    habit_count = len(request.user.habits.all())
    return JsonResponse({"habit_count": habit_count})