from flask import Flask, render_template, request, redirect
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from pymongo import MongoClient
import hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64
import datetime
import os

app = Flask(__name__)

# MongoDB connection
client = MongoClient("mongodb://localhost:27017/")
db = client["pharma_supply_chain"]
supplier_collection = db["supplier"]

# Blockchain storage
blockchain_data = []

# Block class for blockchain
class Block:
    def __init__(self, index, timestamp, data, previous_hash):
        self.index = index  # Block number
        self.timestamp = timestamp  # Time of block creation
        self.data = data  # Block content (e.g., drug info)
        self.previous_hash = previous_hash  # Hash of the previous block
        self.hash = self.calculate_hash()  # Generate hash for the block

    def calculate_hash(self):
        block_string = f"{self.index}{self.timestamp}{self.data}{self.previous_hash}"
        return hashlib.sha256(block_string.encode()).hexdigest()[:16]

# Initialize blockchain with a genesis block
def initialize_blockchain():
    if len(blockchain_data) == 0:
        genesis_block = Block(0, str(datetime.datetime.now()), "Genesis Block", "0")
        blockchain_data.append({
            "index": genesis_block.index,
            "timestamp": genesis_block.timestamp,
            "data": genesis_block.data,
            "previous_hash": genesis_block.previous_hash,
            "hash": genesis_block.hash
        })

# Function to send email using SendGrid
def send_email_to_user(user_email, product_name, amount):
    # Replace with your SendGrid API Key
    sendgrid_api_key = os.getenv("SENDGRID_API_KEY")  # Use an environment variable for security
    if not sendgrid_api_key:
        print("SendGrid API Key not set. Please configure it.")
        return

    message = Mail(
        from_email='karthikb@bitm.edu.in',  # Replace with your verified email
        to_emails='saikiranjavalkar@gmail.com',
        subject='Your Product Receipt',
        html_content=f"""
        <h1>Thank You for Your Purchase!</h1>
        <p>Dear Customer,</p>
        <p>Your product <strong>{product_name}</strong> has been successfully delivered.</p>
        <p><strong>Amount:</strong> ${amount}</p>
        <p>We appreciate your business and look forward to serving you again!</p>
        """
    )
    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        print(f"Email sent successfully! Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {str(e)}")

# Routes for Supplier
@app.route('/')
@app.route('/supplier', methods=['GET'])
def supplier():
    return render_template('supplier_main.html')

@app.route('/supplier/add', methods=['POST'])
def add_drug():
    drug_details = {
        "drug_id": request.form["drug_id"],
        "drug_name": request.form["drug_name"],
        "expiration_date": request.form["expiration_date"],
        "recipient": request.form["recipient"],
        "status": "Created"
    }
    supplier_collection.insert_one(drug_details)

    # Add to blockchain
    previous_hash = blockchain_data[-1]["hash"] if len(blockchain_data) > 0 else "0"
    new_block = Block(len(blockchain_data), str(datetime.datetime.now()), drug_details, previous_hash)
    blockchain_data.append({
        "index": new_block.index,
        "timestamp": new_block.timestamp,
        "data": str(drug_details),
        "previous_hash": new_block.previous_hash,
        "hash": new_block.hash
    })

    return redirect('/supplier')

# Routes for Manufacturer
@app.route('/manufacturer', methods=['GET'])
def manufacturer():
    drugs = list(supplier_collection.find())
    return render_template('manufacturer.html', drugs=drugs)

@app.route('/manufacturer/update', methods=['POST'])
def update_drug():
    drug_id = request.form["drug_id"]
    new_recipient = request.form["recipient"]
    
    supplier_collection.update_one(
        {"drug_id": drug_id},
        {"$set": {"recipient": new_recipient, "status": "Processed by Manufacturer"}}
    )

    # Add to blockchain
    previous_hash = blockchain_data[-1]["hash"]
    updated_block = Block(len(blockchain_data), str(datetime.datetime.now()), f"Manufacturer updated {drug_id}", previous_hash)
    blockchain_data.append({
        "index": updated_block.index,
        "timestamp": updated_block.timestamp,
        "data": f"Manufacturer updated {drug_id}",
        "previous_hash": updated_block.previous_hash,
        "hash": updated_block.hash
    })

    return redirect('/manufacturer')

# Routes for Distributor
@app.route('/distributor', methods=['GET'])
def distributor():
    drugs = list(supplier_collection.find({"status": "Processed by Manufacturer"}))
    return render_template('distributor.html', drugs=drugs)

@app.route('/distributor/update', methods=['POST'])
def distributor_update():
    drug_id = request.form["drug_id"]
    new_recipient = request.form["recipient"]
    
    supplier_collection.update_one(
        {"drug_id": drug_id},
        {"$set": {"recipient": new_recipient, "status": "Dispatched by Distributor"}}
    )

    # Add to blockchain
    previous_hash = blockchain_data[-1]["hash"]
    updated_block = Block(len(blockchain_data), str(datetime.datetime.now()), f"Distributor updated {drug_id}", previous_hash)
    blockchain_data.append({
        "index": updated_block.index,
        "timestamp": updated_block.timestamp,
        "data": f"Distributor updated {drug_id}",
        "previous_hash": updated_block.previous_hash,
        "hash": updated_block.hash
    })

    return redirect('/distributor')

# Routes for Customer
@app.route('/customer')
def customer_dashboard():
    return render_template('customer_dashboard.html', blockchain=blockchain_data)

@app.route('/progress_graph')
def progress_graph():
    fig, ax = plt.subplots()

    # Extract data for plotting
    x = [block['index'] for block in blockchain_data]
    y = [block['data'] for block in blockchain_data]
    hashes = [block['hash'] for block in blockchain_data]

    ax.plot(x, [i for i in range(len(y))], marker='o', color='skyblue')
    for i, txt in enumerate(hashes):
        ax.annotate(f"Block {x[i]} | {txt}", (x[i], i))

    ax.set_xlabel("Block Index")
    ax.set_ylabel("Progress")
    ax.set_title("Blockchain Progress")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')  # Save plot to the buffer
    buf.seek(0)
    graph_url = base64.b64encode(buf.getvalue()).decode()
    buf.close()
    plt.close(fig)  # Close the figure to free resources
    return f'<img src="data:image/png;base64,{graph_url}" />'

@app.route('/confirm_delivery', methods=['POST'])
def confirm_delivery():
    drug_id = request.form["drug_id"]
    user_email = request.form["user_email"]
    drug_name = request.form["drug_name"]
    amount = request.form["amount"]

    # Update status in MongoDB
    supplier_collection.update_one(
        {"drug_id": drug_id},
        {"$set": {"status": "Delivered"}}
    )

    # Send email receipt
    send_email_to_user(user_email, drug_name, amount)

    return redirect('/customer')

# Initialize blockchain at startup
initialize_blockchain()

if __name__ == "__main__":
    app.run(debug=True, port=5010)
