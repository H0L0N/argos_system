import asyncio
import os
import re
from dotenv import load_dotenv, set_key
import questionary
from rich.table import Table

load_dotenv()

from rich.console import Console
from rich.prompt import Prompt
from rich import print as rprint
from core.bot import Bot
from core.client_factory import TelegramClientFactory
from core.config import ScraperConfig
from database.crud import delete_database
from database.engine import Repository, AgentRepository, init_db
from utils.logger import Logger, LogLevel
from telethon.errors import PeerIdInvalidError  # type:ignore
from sqlalchemy.exc import SQLAlchemyError
from modules.sql_agent import SqlAgent, LlmFormatError
from modules.risk_profiling import run_risk_assessment

VERSION = "1.0.0"

custom_style = questionary.Style(
    [
        ("qmark", "fg:#00e6e6 bold"),
        ("question", "fg:#e5c07b bold"),
        ("answer", "fg:#98c379 bold"),
        ("pointer", "fg:#e06c75 bold"),
        ("highlighted", "fg:#61afef bold"),
        ("instruction", "fg:#5c6370 italic"),
    ]
)


def get_env_or_ask(env_key, prompt_msg, validate_func=None, is_password=False):
    """
    Retrieves an environment variable or prompts the user to enter it interactively.
    
    Args:
        env_key (str): The environment variable key.
        prompt_msg (str): The message to display if prompting.
        validate_func (callable, optional): A function to validate the input.
        is_password (bool, optional): Whether the input is a password (hidden).

    Returns:
        str: The value of the environment variable.

    Raises:
        KeyboardInterrupt: If the user cancels the input (Ctrl+C).
    """
    val = os.getenv(env_key)
    if val:
        return val

    while True:
        if is_password:
            val = questionary.password(prompt_msg, style=custom_style).ask()
        else:
            val = questionary.text(prompt_msg, style=custom_style).ask()

        if val is None:
            raise KeyboardInterrupt()

        if validate_func and val and not validate_func(val):
            continue
        break

    if val:
        save = questionary.confirm(
            f"Save {env_key} to .env for future use?", style=custom_style
        ).ask()
        if save is None:
            raise KeyboardInterrupt()
        if save:
            set_key(".env", env_key, val)
            os.environ[env_key] = val
    return val


def main():
    """
    The entry point of the application. Initializes the environment and loops the main menu.
    
    Raises:
        PeerIdInvalidError: If a Telegram peer ID is invalid.
        ValueError: If configuration values are incorrect.
        Exception: For any other unexpected errors during execution.
    """
    init_db()
    logger = Logger()
    console = Console()

    while True:
        try:
            menu(console, logger)
            break
        except KeyboardInterrupt:
            console.print(
                "\n[bold yellow]Action cancelled by user (Ctrl+C).[/bold yellow]\n"
            )
            Prompt.ask("[dim]Press Enter to return to main menu...[/dim]")
        except PeerIdInvalidError:
            console.print("\n[bold red]❌ Fatal Error: Peer ID Invalid[/bold red]")
            console.print(
                "[red]The Group or Topic ID you entered could not be found, or you lack permission to read it.[/red]\n"
            )
            Prompt.ask("[dim]Press Enter to safely return to the main menu...[/dim]")
        except ValueError as e:
            console.print("\n[bold red]❌ Fatal Configuration Error:[/bold red]")
            console.print(f"[red]Details: {str(e)}[/red]")
            console.print(
                "[italic red]Tip: Check that all IDs, hashes, and API keys are strictly correct.[/italic red]\n"
            )
            Prompt.ask("[dim]Press Enter to safely return to the main menu...[/dim]")
        except Exception as e:
            console.print(
                "\n[bold red]❌ An unexpected terminal error occurred:[/bold red]"
            )
            console.print(f"[red]Details: {str(e)}[/red]\n")
            Prompt.ask("[dim]Press Enter to safely return to the main menu...[/dim]")

    logger.banner(
        "SESSION TERMINATED\n[bold red]Ended analysis[/bold red]",
        color="magenta",
    )


async def try_search(logger: Logger):
    """
    Executes a hardcoded semantic search for testing purposes.
    
    Args:
        logger (Logger): The logger instance to use.
    """
    logger.info("Executing Semantic Search across encrypted database...")
    resultados = await Repository.buscar_mensajes_similares("sexo")

    if len(resultados) == 0:
        logger.warning("No similar concepts found in active buffer.")
        return

    columns = ["ID", "Message Content", "Vector Match Score"]
    rows = [[str(msg.id), msg.text[:100], "MATCH CONFIRMED"] for msg in resultados]

    logger.display_table("SEMANTIC ANALYSIS RESULTS", columns, rows)


def menu(console: Console, logger: Logger):
    """
    Renders and manages the main interactive application menu.
    
    Args:
        console (Console): The Rich console instance.
        logger (Logger): The logger instance.

    Raises:
        KeyboardInterrupt: If the user cancels the menu selection.
    """
    while True:
        console.clear()
        logger.banner(
            f"AI Emotion and Risk Assesment System\n[dim]Initializing analyzer...[/dim]\nVersion {VERSION}",
            color="bright_blue",
        )

        console.print(
            "[italic yellow]Notice: Configuration (API IDs, Keys, etc.) can be pre-defined in a .env file. "
            "Missing values will be requested interactively.[/italic yellow]\n"
        )
        console.print(
            "[dim]Tip: You can press Ctrl+C at any time to safely cancel and return to this menu.[/dim]\n"
        )

        try:
            option = questionary.select(
                "Select an action:",
                choices=["Scrape", "Analyze", "Risk Assessment", "Settings / Status", "Reset Database", "Exit"],
                style=custom_style,
            ).ask()
            if option is None:
                raise KeyboardInterrupt()
        except KeyboardInterrupt:
            print("\n")
            logger.info("Okey dockey, bye bye!")
            break

        if option == "Scrape":
            scrape(console)
        elif option == "Analyze":
            analyze(console, logger)
        elif option == "Risk Assessment":
            risk_assessment(console, logger)
        elif option == "Settings / Status":
            status(console, logger)
        elif option == "Reset Database":
            reset_database(console, logger)
        else:
            logger.info("Okey dockey, bye bye!")
            break


def status(console: Console, logger: Logger):
    """
    Displays the current configuration status of required environment variables.
    
    Args:
        console (Console): The Rich console instance.
        logger (Logger): The logger instance.
    """
    console.clear()
    logger.banner("SYSTEM STATUS", color="cyan")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Configuration", width=25)
    table.add_column("Status", width=15)

    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    phone = os.getenv("PHONE_NUMBER")
    openai = os.getenv("OPENAI_API_KEY")

    table.add_row(
        "Telegram API ID",
        "[green]✅ Loaded[/green]" if api_id else "[red]❌ Missing[/red]",
    )
    table.add_row(
        "Telegram API Hash",
        "[green]✅ Loaded[/green]" if api_hash else "[red]❌ Missing[/red]",
    )
    table.add_row(
        "Phone Number", "[green]✅ Loaded[/green]" if phone else "[red]❌ Missing[/red]"
    )
    table.add_row(
        "OpenAI API Key",
        "[green]✅ Loaded[/green]" if openai else "[red]❌ Missing[/red]",
    )

    console.print(table)
    console.print()
    Prompt.ask("[dim]Press Enter to return to the main menu...[/dim]")


def reset_database(console: Console, logger: Logger):
    """
    Deletes and recreates all database tables after double user confirmation.

    Args:
        console (Console): The Rich console instance.
        logger (Logger): The logger instance.
    """
    console.clear()
    logger.banner("⚠ DATABASE RESET", color="red")

    console.print(
        "[bold red]This will permanently delete ALL scraped messages, "
        "risk profiles, and analysis data.[/bold red]\n"
    )

    confirm = questionary.confirm(
        "Are you sure you want to reset the database?",
        default=False,
        style=custom_style,
    ).ask()

    if confirm is None:
        raise KeyboardInterrupt()

    if not confirm:
        console.print("[green]Database reset cancelled.[/green]\n")
        Prompt.ask("[dim]Press Enter to return to the main menu...[/dim]")
        return

    # Double confirmation
    confirm_final = questionary.confirm(
        "⚠ FINAL WARNING: This action is IRREVERSIBLE. Proceed?",
        default=False,
        style=custom_style,
    ).ask()

    if confirm_final is None:
        raise KeyboardInterrupt()

    if not confirm_final:
        console.print("[green]Database reset cancelled.[/green]\n")
        Prompt.ask("[dim]Press Enter to return to the main menu...[/dim]")
        return

    try:
        delete_database()
        init_db()
        logger.success("Database has been reset. All tables recreated empty.")
    except Exception as e:
        logger.error("Failed to reset database", exc=e)

    console.print()
    Prompt.ask("[dim]Press Enter to return to the main menu...[/dim]")


def risk_assessment(console: Console, logger: Logger):
    """
    Runs a semantic risk assessment for all persons in the database,
    comparing message embeddings against pre-defined risky topic vectors.

    Displays a color-coded dashboard sorted by risk score (highest first).

    Args:
        console (Console): The Rich console instance.
        logger (Logger): The logger instance.
    """
    from database.engine import Session, engine

    console.clear()
    logger.banner("RISK ASSESSMENT MODE", color="red")

    console.print(
        "[dim]Analyzing all messages against threat reference vectors...[/dim]\n"
    )

    try:
        with Session(engine) as session:
            results = run_risk_assessment(session, logger)
            session.commit()

            if not results:
                console.print(
                    "\n[bold yellow]⚠ No persons found in the database.[/bold yellow]"
                )
                console.print(
                    "[italic yellow]Tip: Run 'Scrape' first to collect messages before assessing risk.[/italic yellow]\n"
                )
                Prompt.ask("[dim]Press Enter to return to the main menu...[/dim]")
                return

            # Build the results table
            table = Table(
                title="[bold red]🎯 Semantic Risk Assessment Results[/bold red]",
                show_header=True,
                header_style="bold bright_red",
                border_style="red",
                show_lines=True,
            )
            table.add_column("Person", width=20)
            table.add_column("Messages", justify="center", width=10)
            table.add_column("Security Score", justify="center", width=15)
            table.add_column("Risk Level", justify="center", width=15)
            table.add_column("Top Threat Category", width=30)

            for person, score, top_category, msg_count in results:
                # Color-code based on score
                if score >= 3.0:
                    score_display = f"[bold red]{score:.2f}[/bold red]"
                    level_display = "[bold red]🔴 HIGH[/bold red]"
                elif score >= 1.0:
                    score_display = f"[bold yellow]{score:.2f}[/bold yellow]"
                    level_display = "[bold yellow]🟡 MEDIUM[/bold yellow]"
                else:
                    score_display = f"[green]{score:.2f}[/green]"
                    level_display = "[green]🟢 LOW[/green]"

                category_display = top_category if top_category else "[dim]None detected[/dim]"

                table.add_row(
                    person.name,
                    str(msg_count),
                    score_display,
                    level_display,
                    category_display,
                )

            console.print(table)
            console.print()

            # Summary stats
            high_risk = sum(1 for _, s, _, _ in results if s >= 3.0)
            medium_risk = sum(1 for _, s, _, _ in results if 1.0 <= s < 3.0)
            low_risk = sum(1 for _, s, _, _ in results if s < 1.0)

            console.print(f"  [bold]Total Persons Assessed:[/bold] {len(results)}")
            console.print(f"  [bold red]🔴 High Risk:[/bold red] {high_risk}")
            console.print(f"  [bold yellow]🟡 Medium Risk:[/bold yellow] {medium_risk}")
            console.print(f"  [green]🟢 Low Risk:[/green] {low_risk}")
            console.print()

    except Exception as e:
        console.print(
            "\n[bold red]❌ An error occurred during risk assessment:[/bold red]"
        )
        console.print(f"[red]Details: {str(e)}[/red]\n")

    Prompt.ask("[dim]Press Enter to return to the main menu...[/dim]")


def analyze(console: Console, logger: Logger):
    """
    Enters the interactive SQL Agent mode for querying the database in natural language.
    
    Args:
        console (Console): The Rich console instance.
        logger (Logger): The logger instance.

    Raises:
        LlmFormatError: If the LLM generates an invalid response.
        SQLAlchemyError: If the generated SQL query is syntactically incorrect.
        Exception: For unexpected errors during analysis.
    """
    console.clear()
    logger.banner("ANALYZE MODE", color="cyan")

    console.print(
        "[dim]Tip: You can press Ctrl+C at any time to safely cancel and return to the main menu.[/dim]\n"
    )

    openai_api_key = get_env_or_ask(
        "OPENAI_API_KEY", "Enter OpenAI API Key:", is_password=True
    )

    try:
        agent = SqlAgent(api_key=openai_api_key)
    except Exception as e:
        logger.error("Failed to initialize SQL Agent", exc=e)
        Prompt.ask("[dim]Press Enter to safely return to the main menu...[/dim]")
        return

    while True:
        question = Prompt.ask(
            "\n[bold green]Ask a question about the database[/bold green]"
        )
        if question.strip().lower() in ["exit", "back", "q", "quit"]:
            break

        try:
            logger.debug("Generating SQL query...")
            sql_query = asyncio.run(agent.create_sql_query(question))

            logger.debug(f"Generated SQL: \n{sql_query}")

            results = AgentRepository.execute_query(sql_query)

            if not results:
                logger.warning("No results found for that query.")
                continue

            # Formatting results to table
            columns = list(results[0].keys())
            rows = [[str(row.get(col, ""))[:100] for col in columns] for row in results]

            logger.display_table("Analysis Results", columns, rows)

        except LlmFormatError as e:
            logger.error(f"The LLM generated an invalid format: {e}")
        except SQLAlchemyError as e:
            logger.error(
                "The LLM generated a syntactically incorrect query or accessed a non-existent column."
            )
            logger.debug(f"Details: {e}")
        except Exception as e:
            logger.error("An unexpected error occurred during execution.", exc=e)


def scrape(console: Console):
    """
    Configures and starts the Telegram scraping process.
    
    Args:
        console (Console): The Rich console instance.

    Raises:
        KeyboardInterrupt: If the user cancels scraping.
        ValueError: If configuration/IDs provided are invalid.
        Exception: For fatal errors during bot execution.
        BaseException: For critical system-level errors.
    """
    console.clear()
    console.print(
        "[dim]Tip: You can press Ctrl+C at any time to safely cancel and return to the main menu.[/dim]\n"
    )

    # initial scrape config
    log_level_str = questionary.select(
        "Select log level:",
        choices=[level.name for level in LogLevel],
        style=custom_style,
    ).ask()
    if not log_level_str:
        raise KeyboardInterrupt()
    log_level = log_level_str

    phone_number = get_env_or_ask(
        "PHONE_NUMBER",
        "Enter phone number for discrete scrapping (e.g. +1234567890):",
        lambda x: bool(re.match(r"^\+?[1-9]\d{5,14}$", x))
        or rprint(
            "[bold red]❌ Invalid phone format. Please enter a valid number.[/bold red]"
        ),
    )

    while True:
        group_str = questionary.text(
            "Enter target group ID (numbers only):", style=custom_style
        ).ask()
        if group_str is None:
            raise KeyboardInterrupt()
        group_clean = group_str.strip().lstrip("-")
        if group_clean.isdigit():
            target_group_id = int(group_str.strip())
            break
        console.print(
            "[bold red]❌ Error: Group ID must be a valid integer.[/bold red]"
        )

    is_private = questionary.confirm("Is this group private?", style=custom_style).ask()
    if is_private is None:
        raise KeyboardInterrupt()
    if is_private:
        target_str = str(target_group_id)
        if not target_str.startswith("-100"):
            target_group_id = int(f"-100{target_str.lstrip('-')}")

    is_topic = questionary.confirm(
        "Do you want to scrape only a specific topic?", style=custom_style
    ).ask()
    if is_topic is None:
        raise KeyboardInterrupt()

    target_topic_id = None
    if is_topic:
        while True:
            topic_str = questionary.text("Enter topic ID:", style=custom_style).ask()
            if topic_str is None:
                raise KeyboardInterrupt()
            if topic_str.strip().isdigit():
                target_topic_id = int(topic_str.strip())
                break
            console.print(
                "[bold red]❌ Error: Topic ID must be a valid integer.[/bold red]"
            )

    api_id_str = get_env_or_ask(
        "API_ID",
        "Enter Telegram API ID:",
        lambda x: x.strip().isdigit()
        or rprint("[bold red]❌ Must be a numeric ID.[/bold red]"),
    )
    api_id = int(api_id_str.strip())

    api_hash = get_env_or_ask(
        "API_HASH",
        "Enter Telegram API Hash:",
        lambda x: len(x.strip()) >= 10
        or rprint("[bold red]❌ API Hash seems too short.[/bold red]"),
    )

    scraper_config = ScraperConfig(
        target_group_id=target_group_id,
        target_topic_id=target_topic_id,
        scraping_interval_seconds=60,
        log_level=LogLevel[log_level],
    )

    # dependency injection
    logger = Logger(level=scraper_config.log_level)
    factory = TelegramClientFactory(logger, api_id, api_hash, phone_number)
    bot = Bot(scraper_config, factory, logger)

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]⚠ Scraping interrupted by user.[/bold yellow]\n")
        Prompt.ask("[dim]Press Enter to return to the main menu...[/dim]")
    except ValueError as e:
        console.print("\n[bold red]❌ Fatal Configuration Error:[/bold red]")
        console.print(f"[red]Details: {str(e)}[/red]")
        console.print(
            "\n❗[italic red] [bold]Tip:[/bold] Check that all IDs, hashes, and API keys are strictly correct.[/italic red]\n"
        )
        Prompt.ask("[dim]Press Enter to safely return to the main menu...[/dim]")
    except Exception as e:
        console.print(
            "\n[bold red]❌ A fatal error occurred during the scraping process:[/bold red]"
        )
        console.print(f"[red]Details: {str(e)}[/red]\n")
        console.print(
            "[italic red]Tip: This could be due to a dropped connection, invalid API credentials, or lacking permissions to read the group.[/italic red]\n"
        )
        Prompt.ask("[dim]Press Enter to safely return to the main menu...[/dim]")
    except BaseException as e:
        console.print("\n[bold red]❌ An unexpected system error occurred:[/bold red]")
        console.print(f"[red]Details: {str(e)}[/red]\n")
        Prompt.ask("[dim]Press Enter to safely return to the main menu...[/dim]")
        raise


if __name__ == "__main__":
    main()
