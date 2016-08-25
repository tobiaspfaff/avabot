import os
import pysftp
import requests
import time
import uuid

from slackclient import SlackClient

# avabot's ID as an environment variable
BOT_ID = os.environ.get("BOT_ID")
BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
FTP_URL = os.environ.get('FTP_URL')
FTP_USER = os.environ.get('FTP_USER')
FTP_PASS = os.environ.get('FTP_PASS')
FTP_DIR = os.environ.get('FTP_DIR')
MAGIC_WORD = os.environ.get('MAGIC_WORD')

# constants
AT_BOT = "<@" + BOT_ID + ">"

# instantiate Slack & Twilio clients
slack_client = SlackClient(BOT_TOKEN)


class Message(object):
    def __init__(self, type, channel, text):
        self.type = type
        self.channel = channel
        self.text = text
        self.response = "Do you have any friends you can share?"

class File(Message):
    def __init__(self, file_id):
        Message.__init__(self, 'file', None, None)
        self.response = self.download_image(file_id)

    def download_image(self, file_id):
        """ Downloads an image and returns a response. Returns None on failure
            or if there is nothing to say. Sets the channel. """
        # Get the file info from the File ID
        response = slack_client.api_call("files.info", file=str(file_id))
        if not response['ok']:
            return None
        user_id = response['file']['user']
        self.channel = user_id
        size = response['file']['size']
        filetype = response['file']['filetype']
        title = response['file']['title']
        if MAGIC_WORD not in title:
            return None
        elif size > 1024 * 1000:
            return "I can't handle images more than a megabyte."
        elif filetype != "jpg" and filetype != "png":
            return "I can only handle PNGs and JPGs"

        # Download the file (with authentication)
        url = response['file']['url_private']
        header = {'Authorization': 'Bearer '+BOT_TOKEN}
        fileResponse = requests.post(url, headers=header)
        if not fileResponse.ok:
            return "I could not download the image at " + url

        # Where should the file go?
        subdir = get_username_from_id(user_id)
        output_dir = os.path.join('downloadedImages', subdir)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_filename = str(uuid.uuid4()) + '.' + filetype
        output_filepath = os.path.join(output_dir, output_filename)

        # Read and save the file
        with open(output_filepath, 'wb') as handle:
            for block in fileResponse.iter_content(1024):
                handle.write(block)

        # Upload the file
        upload_image(output_filepath)

        return "Thanks for the tip, friend!"

def create_js_list(file_list, output_filepath):
    """ Writes a javascript file containing a list of images outlined in
        file_list. Assumes there is only one avabot server running. """
    with open(output_filepath, 'wb') as myfile:
        myfile.write('function getImages() {\n')
        myfile.write('  return [\n')
        for i in file_list:
            if i:
                myfile.write('    "' + i + '",\n')
        myfile.write('] }')

def upload_image(localFile):
    """ Upload the image at localFile to the FTP_DIR with the same name. """
    with pysftp.Connection(FTP_URL, username=FTP_USER, password=FTP_PASS) as sftp:
        with sftp.cd(FTP_DIR):
            # Put the image
            sftp.put(localFile)

            # Add the image's filename to uploadedFiles.txt
            if localFile: # will only be false on test cases
                with open('uploadedFiles.txt', "a") as myfile:
                    myfile.write(os.path.basename(localFile) + "\n")

            # Add contents of uploadedFiles.txt to a js list
            with open('uploadedFiles.txt', "r") as myfile:
                file_list = myfile.read().split('\n')
            output_filepath = 'imagelist.js'
            create_js_list(file_list, output_filepath)
            sftp.put(output_filepath)

def handle_command(message):
    if message.response is None:
        print "Ignoring request of type ", message.type
        return

    print "Sending '" + message.response + "' to " + message.channel
    slack_client.api_call("chat.postMessage",
                          channel=message.channel,
                          text=message.response,
                          as_user=True)

def get_username_from_id(uid):
    """ Returns the username corresponding to the ID, or on failure,
        the user ID itself. """
    response = slack_client.api_call("users.info", user=uid)
    if not response['ok']:
        return uid
    else:
        return response['user']['name'] + "-" + uid

def parse_slack_output(slack_rtm_output):
    """ The Slack Real Time Messaging API is an events firehose.
        this parsing function returns None unless a message is
        directed at the Bot, based on its ID.  """
    output_list = slack_rtm_output
    if output_list and len(output_list) > 0:
        for output in output_list:
            if output['type'] == 'message' and 'text' in output:
                text = output['text']
                if text.startswith(AT_BOT):
                    return Message(type='text',
                                   channel=output['channel'],
                                   text=text.split(AT_BOT)[1].strip().lower())
            elif output['type'] == 'file_shared':
                file_id = output['file_id']
                return File(file_id=file_id)
    return None

if __name__ == "__main__":
    READ_WEBSOCKET_DELAY = 1 # 1 second delay between reading from firehose
    if slack_client.rtm_connect():
        print("Ava is listening")
        while True:
            message = parse_slack_output(slack_client.rtm_read())
            if message:
                handle_command(message)
            time.sleep(READ_WEBSOCKET_DELAY)
    else:
        print("Connection failed. Invalid Slack token or bot ID?")
