import datetime
from django.core.exceptions import ObjectDoesNotExist
from django_socketio import events
import time

from websocket_wall.banned_words import is_content_valid
from wechat_wall.models import *


def select_users_by_openid(openid):
    return User.objects.filter(openid=openid)


def get_admin():
    return User.objects.get(name="root")


def get_message_by_id(message_id):
    return Message.objects.get(message_id=message_id)


def insert_message(user, content, time, status):
    new_message = Message.objects.create(user=user, content=content,
                                         time=time, status=status)
    message_num = user.message_num
    user.message_num = message_num + 1
    user.save()
    return new_message


def get_whether_review():
    try:
        admin = get_admin()
    except ObjectDoesNotExist:
        return 0
    whether_review = admin.openid
    return int(whether_review)


@events.on_message(channel="^")
def message(request, socket, context, message):
    return_message = {'type': message['type']}
    if message['type'] == 'user_message':
        users = select_users_by_openid(message['openid'])
        if not users:
            return_message['result'] = 'NoUser'
            socket.send(return_message)
            return
        user = users[0]
        content = message['content']
        if not is_content_valid(content):
            return_message['result'] = 'BannedContent'
            socket.send(return_message)
            return
        now = datetime.datetime.now()
        status = 1 - get_whether_review()
        try:
            new_message = insert_message(user, content, now, status)
            return_message = make_success_message(new_message)
            return_message['type'] = 'user_message'
            if status == 1:
                socket.send_and_broadcast_channel(return_message, 'wall')
            else:
                socket.broadcast_channel(return_message, 'admin')
            return
        except Exception as e:
            print 'Error occured!!!!!!' + str(e)
            return_message['result'] = 'Error'
            socket.send(return_message)
            return

    elif message['type'] == 'admin_message':
        try:
            admin = get_admin()
        except ObjectDoesNotExist:
            return_message['result'] = 'Error'
            socket.send(return_message)
            return
        content = message['content']
        status = 2
        now = datetime.datetime.now()
        try:
            new_message = insert_message(admin, content, now, status)
            return_message = dict(return_message, **make_success_message(new_message))
            socket.broadcast_channel(return_message, 'wall')
            return
        except Exception as e:
            print 'Error occured!!!!!!' + str(e)
            return_message['result'] = 'Error'
            socket.send(return_message)
            return

    elif message['type'] == 'review_message':
        handler_list = {
            'pass': pass_message,
            'reject': reject_message,
        }
        messages_id = message['message_id'].split(',')
        return_message['msg_id'] = ''
        for msg_id in messages_id:
            if not handler_list[message['action']](msg_id):
                return_message['result'] = 'error'
                break
            if message['action'] == 'pass':
                broadcast_message(socket, msg_id)
            return_message['msg_id'] += (msg_id + ',')
        if not ('result' in return_message):
            return_message['action'] = message['action']
            return_message['result'] = 'success'
        return_message['msg_id'] = return_message['msg_id'][:-1] + ''
        socket.send(return_message)
        return


def make_success_message(message):
    return_message = {'id': message.message_id, 'openid': message.user.openid,
                      'avatar': message.user.photo, 'name': message.user.name,
                      'content': message.content, 'result': 'Success'}
    return return_message


def pass_message(msg_id):
    try:
        message = Message.objects.get(message_id=msg_id)
        message.status = 1
        message.save()
        return True
    except ObjectDoesNotExist:
        return False


def reject_message(msg_id):
    try:
        message = Message.objects.get(message_id=msg_id)
        message.status = -1
        message.save()
        return True
    except ObjectDoesNotExist:
        return False


def broadcast_message(socket, message_id):
    try:
        message = get_message_by_id(message_id)
        return_message = make_success_message(message)
        return_message['type'] = 'user_message'
        socket.broadcast_channel(return_message, 'wall')
    except ObjectDoesNotExist:
        return
