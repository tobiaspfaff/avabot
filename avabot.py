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
FILE_LIST = os.environ.get('FILE_LIST')

# constants
AT_BOT = "<@" + BOT_ID + ">"

# instantiate Slack & Twilio clients
slack_client = SlackClient(BOT_TOKEN)


class Message(object):
    def __init__(self, type, channel, text):
        self.type = type
        self.channel = channel
        self.text = text

class File(Message):
    def __init__(self, file_id):
        Message.__init__(self, 'file', None, None)
        self.file_id = file_id

    def download_image(self):
        # Get the file info from the File ID
        response = slack_client.api_call("files.info", file=str(self.file_id))
        if not response['ok']:
            return None
        user_id = response['file']['user']
        self.channel = user_id
        size = response['file']['size']
        filetype = response['file']['filetype']
        title = response['file']['title']
        if 'rick' not in title:
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
        output_dir = user_id
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
    with open(output_filepath, 'wb') as myfile:
        myfile.write('function getImages() {\n')
        myfile.write('  return [\n')
        for i in file_list:
            if i:
                myfile.write('    "' + i + '",\n')
        myfile.write('] }')

def upload_image(localFile):
    with pysftp.Connection(FTP_URL, username=FTP_USER, password=FTP_PASS) as sftp:
        with sftp.cd(FTP_DIR):
            # Put the image
            sftp.put(localFile)

            # Add the image's filename to FILE_LIST
            if localFile: # will only be false on test cases
                with open(FILE_LIST, "a") as myfile:
                    myfile.write(os.path.basename(localFile) + "\n")

            # Add contents of FILE_LIST to a js list
            with open(FILE_LIST, "r") as myfile:
                file_list = myfile.read().split('\n')
            output_filepath = 'imagelist.js'
            create_js_list(file_list, output_filepath)
            sftp.put(output_filepath)

def handle_command(message):
    if message.type == 'text':
        response = "Do you have any friends you can share?"
    elif message.type == 'file':
        response = message.download_image()

    if response is None:
        print "Ignoring request of type ", message.type
        return

    print "Sending '" + response + "' to " + message.channel
    slack_client.api_call("chat.postMessage",
                          channel=message.channel,
                          text=response,
                          as_user=True)


def parse_slack_output(slack_rtm_output):
    """
        The Slack Real Time Messaging API is an events firehose.
        this parsing function returns None unless a message is
        directed at the Bot, based on its ID.
    """
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
    #upload_image('U0E68ATT4/1293699a-d85a-4e78-9281-24896e67de86.jpg')
    #exit()
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
