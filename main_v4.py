from flask import Flask, request, send_file, render_template, send_from_directory, url_for, abort, jsonify
import time
from openai import OpenAI
from transformers import GPT2Tokenizer
import genanki
import uuid
from datetime import datetime
import os
import json

client = OpenAI(
    # This is the default and can be omitted
    api_key="[YOUR_API_KEY]",
)

app = Flask(__name__)

instructions = """
You are a bot that creates a set of {num_cards} varied and highly diverse fill-in-the-blank Cloze Anki flashcards from the information given by the user. The output should be in the following format:

#Card 1 (Example)
F: The answer to this question is {{c1::answer}}.
B: None

#Card 2
F: {{c1::Staph}} are gram-positive bacteria.
B: None
...

#Card {num_cards}
F: {{c1::Rome}} is the capital of {{c2::Italy}}
B: None
""".strip()

def query_GPT(input_str, system_prompt):
    '''
    Literally just a helper function that queries GPT
    '''
    return client.chat.completions.create(
          model="gpt-4o",
          messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_str}
            ],
          temperature=0.5,
          top_p=0.9
        ).choices[0].message.content

def chat_GPT(input_messages, system_prompt):
    '''
    Literally just a helper function that queries GPT
    '''
    messages = [{"role": "system", "content": system_prompt}]

    for i, message in enumerate(input_messages):
        if i % 2 == 0:
            messages.append({"role": "user", "content": message})
        else:
            messages.append({"role": "assistant", "content": message})

    return client.chat.completions.create(
          model="gpt-4o",
          messages=messages,
          temperature=0.8
        ).choices[0].message.content

def parse_cards(string):
    cards = string.split("F: ")[1:]
    pairs = []
    for item in cards:
        if len(item) > 0:
            pairs.append([s.strip() for s in item.split("B:")])

    for i in range(0, len(pairs)):
        pairs[i][0] = pairs[i][0].split('\n\n#Card')[0].strip()
        pairs[i][1] = pairs[i][1].split('\n\n#Card')[0].strip()

    return pairs

@app.route('/static/css/<path:path>')
def send_css(path):
    return send_from_directory('static/css', path)

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/", methods=['POST'])
def response():
    global instructions
    start = time.time()
    now = datetime.now()
    current_time = now.strftime("%D:%H:%M:%S").replace('/', ':')

    fn = str(uuid.uuid4()) + ".apkg"

    notes = request.json['notes'].strip()

    num_cards = int(request.json['num_cards'])
    instructions = instructions.replace("{num_cards}", str(num_cards))

    out = query_GPT(notes, instructions)

    with open(f"{current_time.replace(':', '-')}_log_{fn[:-5]}.txt", "w") as f:
        f.write(notes + "\n\n" + instructions + "\n\n" + out + "\n\n" + request.remote_addr + "\n\n" + current_time)
        f.write("\n\nGeneration time: " + str(time.time()-start) + " secs")
        f.write("\n\nAutoanki v2.0")

    cards = parse_cards(out.strip())

    my_model = genanki.Model(
      1607392319,
      'Simple Model',
      fields=[
        {'name': 'Question'},
        {'name': 'Answer'},
      ],
      templates=[
        {
          'name': 'Card 1',
          'qfmt': '{{Question}}',
          'afmt': '{{FrontSide}}<hr id="answer">{{Answer}}',
        },
      ])

    my_deck = genanki.Deck(
      2059400110,
      'Generated Deck')

    for item in cards:
        try:
            if "{{c1::" in item[0]:
                my_note = genanki.Note(
                              model=genanki.CLOZE_MODEL,
                              fields=[item[0], item[1] if item[1] != "None" and "Card #" not in item[1] else ''])
            else:
                my_note = genanki.Note(
                              model=my_model,
                              fields=[item[0], item[1]])
            my_deck.add_note(my_note)
        except:
            pass

    genanki.Package(my_deck).write_to_file(fn)

    #out = out.replace('\n', "<br/>")
    #return index + '\n' + out.strip()

    #return send_file(fn)
    return jsonify({"link": url_for("download", filename=fn)})

@app.route("/")
def home():
    return index

@app.route('/api/professor-response', methods=['POST'])
def professor_response():
    #save request.json to log file, with timestamp and IP address
    with open('log.txt', 'a', encoding='utf-8') as f:
        f.write(time.strftime("[%Y-%m-%d %H:%M:%S]", time.localtime()) + ' ' + request.remote_addr + ' ' + json.dumps(request.json) + '\n')
    chat_history = request.json.get('chat_history')[:-1]
    notes = request.json.get('notes')

    system_prompt = f"""
You are a tutor that generates quiz questions based on the student's notes. The student has provided you with the following notes:
START NOTES
{notes}
END NOTES

You ask the students quiz questions and walk them through the answers if they are having trouble. You can ask follow up questions to your original questions to continue to test knowledge on a particular subject. Separate each new line with `<br>` instead of the normal newline character. Ensure you use `<br>` often to make the output cleaner.
""".strip()
    #parse chat history
    messages = []
    for message in chat_history:
        messages.append(': '.join(message.split(': ')[1:]).strip().replace('\n', '<br>'))

    return jsonify(professor_response=chat_GPT(messages, system_prompt).strip())

@app.route("/download/<filename>")
def download(filename):
    if filename[-5:] != ".apkg":
        with open("unauthorized_accesses.txt", "a") as f:
            f.write(request.remote_addr + " " + filename + " " + str(datetime.now()) + "\n")
        abort(401)
    
    #check if file was created in the last ten minutes
    if os.path.getctime(filename) > time.time() - 600:
        return send_file(filename)
    else:
        with open("unauthorized_accesses.txt", "a") as f:
            f.write(request.remote_addr + " " + filename + " " + str(datetime.now()) + "\n")
        abort(401)

#display case_1.html
@app.route('/quiz.html')
def case_1():
    return render_template('quiz.html')

if __name__ == '__main__':
    # run() method of Flask class runs the application
    # on the local development server.
    app.run(host='0.0.0.0', port=80)
