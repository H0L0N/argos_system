import re
from langchain_community.utilities import SQLDatabase
from langchain_classic.chains import create_sql_query_chain
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI


class LlmFormatError(Exception):
    pass


class SqlAgent:
    """Agent that translates natural language into database SQL queries based on the DB schema."""

    def __init__(
        self,
        api_key: str,
        db_uri: str = "postgresql://sql_agent:sql_agent@localhost:5432/argos_system",
    ):
        """
        Initializes the SQL Agent with database and LLM configurations.

        Args:
            api_key (str): OpenAI API key.
            db_uri (str): PostgreSQL database URI.

        Raises:
            ValueError: If OPENAI_API_KEY is missing.
        """
        if not api_key:
            raise ValueError("OPENAI_API_KEY must be passed explicitly to SqlAgent.")

        self.db = SQLDatabase.from_uri(db_uri)
        self.llm = ChatOpenAI(api_key=api_key, model="gpt-4o", temperature=0)  # type: ignore

        template = """
Given an input question, first create a syntactically correct {dialect} query to run.
Return JUST the SQL query in markdown format. Nothing more.

Only use the following tables:
{table_info}

CRITICAL INSTRUCTION: The table names in this database are SINGULAR (e.g., use 'message', not 'messages'; 'user', not 'users'). 
Do not pluralize table names. Use EXACTLY the table names provided in the schema description.
Pay attention to use only the column names that you can see in the schema description. Also, focus on using correct table names.
Limit your results to {top_k} unless the user explicitly asks for all of them. 

Question: {input}"""

        prompt = PromptTemplate.from_template(template)
        self.chain = create_sql_query_chain(llm=self.llm, db=self.db, prompt=prompt)

    async def create_sql_query(self, user_input: str) -> str:
        """
        Generates a SQL query from natural language input using LangChain and GPT.

        Args:
            user_input (str): The natural language query from the user.

        Returns:
            str: The extracted SQL query string.

        Raises:
            LlmFormatError: If the LLM response does not contain a markdown SQL block.
        """
        response = self.chain.invoke({"question": user_input})
        sql_pattern = r"```sql(.*?)```"
        match_result = re.search(sql_pattern, response, flags=re.DOTALL)

        if match_result:
            return match_result.group(1).strip()
        else:
            raise LlmFormatError("The LLM did not return a valid SQL block.")
