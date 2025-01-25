from googleapiclient.discovery import build
from bs4 import BeautifulSoup
import requests
from config.settings import GOOGLE_API_KEY, GOOGLE_CSE_ID

def web_search(query: str, num_results: int = 3, groq_client=None) -> str:
    try:
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        res = service.cse().list(q=query, cx=GOOGLE_CSE_ID, num=num_results).execute()

        search_results = []
        for item in res.get('items', []):
            title = item.get('title', 'No title')
            link = item.get('link', 'No link')
            snippet = item.get('snippet', 'No snippet')
            search_results.append({"title": title, "link": link, "snippet": snippet})

        if not search_results:
            return "No results found."

        analysis_prompt = f"Analyze these search results and determine which is most relevant to the query '{query}':\n"
        for i, result in enumerate(search_results):
            analysis_prompt += f"{i+1}. Title: {result['title']}\nSnippet: {result['snippet']}\n\n"
        analysis_prompt += "Return only the number of the most relevant result. Look up for the similar words/terms in the link as the query for most priority. If the link is forbidden or any error or any less informative or less relevant website for the user request, then you must move to other links."

        analysis_response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": analysis_prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.5,
            max_tokens=50,
        )
        most_relevant_index = int(analysis_response.choices[0].message.content.strip()) - 1
        most_relevant_url = search_results[most_relevant_index]['link']

        response = requests.get(most_relevant_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        page_content = soup.get_text()

        summary_prompt = f"Based on the following content from {most_relevant_url}, provide a very short that so small which only should include important things and dont bore the user with much information and basic guiding. Just say only key things, concise and informative summary addressing the query '{query}':\n\n{page_content[:4000]}"

        summary_response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": summary_prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=1000,
        )
        summary = summary_response.choices[0].message.content.strip()

        return f"Based on information from {most_relevant_url}:\n\n{summary}"

    except Exception as e:
        return f"An error occurred while searching and analyzing: {str(e)}" 