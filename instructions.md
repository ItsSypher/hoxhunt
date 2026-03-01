### Task
Your task is to build Python tool that uses an LLM to summarize provided list of movie reviews (found in the reviews.json file) and store them to a simple database. Write a script that processes each review through the model and stores results in SQLite. The model should produce at least a very short summary of the review, an estimated rating from 1 to 5, and a sentiment estimation (positive or negative). Design the database schema yourself and document it in the README.

You can use, e.g., a free tier Gemini series model with an API_KEY, which you can generate by following the instructions in https://ai.google.dev/gemini-api/docs/api-key

We don’t expect you to spend lot of time getting good results from the model but rather treat this more like a fast proof of concept. However, you should be prepared to discuss on how to improve the solution in order to make it production ready.

The task is expected to take maximum two to four hours.


### Deliverable
Github repository with all the code and short readme on how to run the tool.

Make the repository private and give read access to the following Github users: @Essi-Tallgren @lauramjpuusola @mxnurmi @arttuarp
