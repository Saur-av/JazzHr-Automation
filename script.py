import requests
import csv
import os
from dataclasses import dataclass
from selenium import webdriver
from time import sleep
from datetime import datetime


EMAIL = ""
PASSWORD = ""
FILE_NAME = "Locations.csv"

@dataclass
class Job:
    title : str
    id : int
    postal : str

def create_job_payload(api_response : dict[str:str],dataframe : list[str]) -> dict[str:str]:
    '''api_response :- Contents from the API Call.
    dataframe :- List With ['usState','usCity','usPostalCode']'''
    api_response["city"] =  dataframe[1]
    api_response["state"] =  dataframe[0]
    api_response["postal"] =  dataframe[2]
    api_response['status'] = 'Open'
    api_response['dateOpened'] = datetime.today().strftime('%Y-%m-%d')
    api_response['updatedAt'] = datetime.today().strftime('%Y-%m-%d')

    return api_response

def close_payload(data : dict[str:str]) -> dict[str:str]:
    '''Change the status of Job to Closed.'''
    data['status'] = 'Closed'

    return data

class Automation:
    def __init__(self):
        self.session = requests.Session()
        self.driver = webdriver.Chrome()
        self.driver.implicitly_wait(10)
        self.driver.maximize_window()

        #Variables
        self.user_account : list[dict] = [] #List of Sub Accounts
        self.selected_account : int | None = None #ID of the Current Sub Account
        self.account_name : str = "" #Name of the Current Sub Account
        self.open_jobs : list[Job] = [] #List of Jobs waiting to be Enriched.
        self.clone_jobs : list[dict] = {} #List of Jobs to be Cloned.
        self.zip_codes = [] #List of all Available Zip codes from "Locations.csv".

    def authenticate(self):
        '''Authenticate the user with the credentials provided.'''
        self.driver.get("https://app.jazz.co/app/v2/login")
        self.driver.find_element("css selector","#email").send_keys(EMAIL)
        self.driver.find_element("css selector","#password").send_keys(PASSWORD)
        
        while "login" in self.driver.current_url:
            if input("Please Login and Press Enter...") == "#":
                break

        self.user_account = self.session.get("https://api.jazz.co/customerManager/hub/accounts?page=1&per_page=100").json() # Get all the accounts | Always <200 Response>
        
    def update_cookies(self):
        '''Update the session cookies with the cookies from the selenium driver.'''
        cookies = self.driver.get_cookies()

        for cookie in cookies:
            self.session.cookies.set(cookie['name'], cookie['value'])

    def select_user(self) -> bool:
        '''Select the user account to work on, Returns True if the account was selected successfully, False otherwise.'''
        if not self.user_account:
            print("There were no user accounts found!")
            return False
        
        max_accounts = len(self.user_account)
        
        if self.selected_account:
            self.driver.get("https://app.jazz.co/app/v2/portal/exit?type=linked") # Exit the current account

        print("Let's Select an user!")
        for index,account in self.user_account:
            print(f"{index} : {account['name']}")
        
        
        while True:
            selection = input("Please select the account you want to work on, Donot Choose an Closed Account: ")
            if selection.isdigit():
                selection = int(selection)
                if selection > 0 and selection < max_accounts:
                    self.driver.get(f"https://app.jazz.co/app/v2/dashboard?cid={self.selected_account}")
                    self.selected_account = self.user_account[selection]['id']
                    self.account_name = self.user_account[selection]['name']
                    print(f"\n Selected Account: {self.account_name}")
                    return True
            print(f"Invalid Choice, Please choose [0-{max_accounts-1}]")
    
    def iterate_over_accounts(self,index):
        #Iterator to select IDs based on the index in the Website.
        if index > 0 and index < len(self.user_account):
            raise IndexError("Index out of range!")
        
        if self.selected_account:
            self.driver.get("https://app.jazz.co/app/v2/portal/exit?type=linked") # Exit the current account
        
        id = self.user_account[index]['id']
        self.driver.get(f"https://app.jazz.co/app/v2/dashboard?cid={self.selected_account}")
        
        self.selected_account = self.user_account[index]['id']
        self.account_name = self.user_account[index]['name']

        print(f"\n Selected Account: {self.account_name}")

    def get_open_jobs(self):
        #Retrives the Jobs currently Opened in the SubAccount
        self.update_cookies()

        permissions = self.session.get(f"https://api.jazz.co/user/me?expand=customer%2Ccustomer.groups%2Ccustomer.plan%2Ccustomer.settings%2Ccustomer.timeZone%2Ccustomer.brand%2CmasterUser%2CpartnerRole%2Crole").json()
        account_id = permissions['id']

        active_jobs = self.session.get(f"https://api.jazz.co/user/{account_id}/job/open?per_page=500").json()

        for job in active_jobs:
            self.open_jobs.append(Job(job['title'], job['id'], job['postal'].zfill(5)))
        
    def scrape_job_details(self):
        #Enriches the Scraped jobs from the get_open_jobs() function.
        self.update_cookies()
        
        for link in self.open_jobs:
            sleep(1)
            id = link.id
            req = self.ses.get(f"https://api.jazz.co/job/{id}?expand=hiringLead%2Cquestionnaire%2Cworkflow%2Cworkflow.workflowSteps%2CsyndicationChannels%2ChasScorecardTemplateJob")
            
            if not req.ok:
                print(f"Job Id : {id}\nError : {req.status_code}\nMessage : {req.text}")
                continue

            job_details = req.json()

            self.clone_jobs.append(job_details)

    def read_zip_codes_from_csv(self):
        #Updates all of the Zip Codes from the "Locations.csv" file.
        self.zip_codes = []
        if not os.path.exists(FILE_NAME):
            raise FileNotFoundError(f"File {FILE_NAME},Not Found!")
        
        with open(FILE_NAME, newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                self.zip_codes.append(row)

    def get_next_zip_code_line(self,target_zip):
        #Looks for the postal code and returns the Next Postal code to be updated.
        if isinstance(target_zip,tuple):
            target_zip = target_zip[0]

        target_zip = target_zip.zfill(5)

        for i, row in enumerate(self.zip_codes):
            if target_zip in row:
                next_index = (i + 1) % len(self.zip_codes)  # Wrap around to the beginning if end of list is reached
                if next_index == 1:
                    next_index = 2 # Skip the header row
                return self.zip_codes[next_index]
        print(f"Target zip code not found in the list. {target_zip} is not in the Locations.csv file.")
        return None

    def clone(self):
        '''Check for the Open Jobs in the SubAccount.
        Tries to Close the Job Posting.
        Then Tries to Clone Job Posting with the next Location.
        '''
        self.update_cookies()

        for job in self.clone_jobs:
            #Get Details for the new Job
            postal = job['postal']
            if isinstance(postal,tuple):
                postal = postal[0]

            location = self.get_next_zip_code_line(postal)

            if not location:
                print(f"It appears {job['id']} | {job['title']} is not in the {FILE_NAME}! Skipping...")
                continue
            
            #Close the job
            payload = close_payload(job)

            url = f"https://api.jazz.co/job?expand=syndicationChannels%2ChiringLead"
            req = self.session.put(url, json=payload)

            if req.ok:
                print(f"Closed {job['title']} | {job['id']}!")
            else:
                print(f"Failed to close a job, \n Job Id : {payload['id']}\nError : {req.status_code}\nMessage : {req.text}")
            sleep(2)

            #Clone the job
            payload = create_job_payload(job,location)

            url = f"https://api.jazz.co/job?isCloning=true&oldJobId={job["id"]}&expand=classifications%2ChiringLead%2Cquestionnaire%2Cquestionnaire.questions%2Cworkflow%2Cworkflow.workflowSteps%2Cworkflow.automatedReply"
            req = self.session.post(url,json=payload)

            if not req.ok:
                print(f"Failed to clone the job! \n Job Id : {payload['id']}\nError : {req.status_code}\nMessage : {req.text}")
                continue
            
            

            data_payload = req.json()
            req = self.session.put(f"https://api.jazz.co/job/field", json={"customFieldValues": [], "id": data_payload['id']})
            
            new_job_id = req.json()['id']

            if req.ok:
                    print(f"Successfully Cloned the job.  {new_job_id} | {job['title']}!")
            else:
                print(f"Failed to Open the Cloned the job! \n Job Id : {new_job_id}\nError : {req.status_code}\nMessage : {req.text}")
            return

    def shutdown(self):
        '''Shutdown the browser.'''
        self.driver.quit()
        self.session.close()


if not os.path.exists(FILE_NAME):
    raise FileNotFoundError(f"The Config File {FILE_NAME} was not Found! Please Set the Correct Path in the Script.")

jazz = Automation()
jazz.authenticate()

def menu():
    if jazz.selected_account is not None:
        print(f"Selected Account: {jazz.account_name}\n\n")
    msg = f"""
"Welcome to JazzHR Automation Script!
    1. Run Main Automation [Scrape Jobs/Close Jobs/Open Jobs].
    2. Select User.
    3. Get Job Details.
    4. Clone Jobs.
    5. Exit
    """
    print(msg)

while True:
    os.system('cls')
    menu()
    choice = input("Please select an option: ")
    if choice == "1":
        for index in range(len(jazz.user_account)):
            jazz.iterate_over_accounts(index)
            jazz.get_open_jobs()
            jazz.scrape_job_details()
            jazz.clone()
    elif choice == "2":
        jazz.select_user()
    elif choice == "3":
        jazz.get_open_jobs()
        jazz.scrape_job_details()
    elif choice == "4":
        jazz.clone_jobs()
    elif choice == "5":
        jazz.shutdown()
        exit()
