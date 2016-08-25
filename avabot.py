import ftplib
import os
import requests
import time

from slackclient import SlackClient


# avabot's ID as an environment variable
BOT_ID = os.environ.get("BOT_ID")
BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')

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
            return "I don't understand your message."
        userId = response['file']['user']
        self.channel = userId
        size = response['file']['size']
        filetype = response['file']['filetype']
        if size > 1024 * 1000:
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
        outputDir = userId
        if not os.path.exists(outputDir):
            os.makedirs(outputDir)
        outputFilename = os.path.join(outputDir, 'output.' + filetype)

        # Read and save the file
        with open(outputFilename, 'wb') as handle:
            for block in fileResponse.iter_content(1024):
                handle.write(block)

        return "Thanks for the tip, friend!"

def upload_image():
    session = ftplib.FTP('server.address.com','USERNAME','PASSWORD')

def handle_command(message):
    if message.type == 'text':
        response = "Do you have any friends you can share?"
    elif message.type == 'file':
        response = message.download_image()

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
