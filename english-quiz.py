import anthropic
import json
import os
import random
import requests
from dotenv import load_dotenv
from shared import ts, parse_json_response, post_to_discord_safe

# Load secrets from .env for local testing
load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
QUIZ_GIST_ID = os.environ.get("QUIZ_GIST_ID", "")

CATEGORIES = [
    "idioms",                       # Fixed expressions with figurative meaning (e.g., 'spill the beans')
    "phrasal verbs",                # Verb + particle combinations (e.g., 'give up', 'look after')
    "vocabulary",                   # General word meaning and usage
    "verb tenses",                  # Past, present, future, perfect, continuous forms
    "prepositions",                 # In, on, at, for, since, of, etc.
    "slang",                        # Informal, colloquial words (e.g., 'gonna', 'lit')
    "grammar",                      # Sentence structure, conditionals, passive voice, etc.
    "pronunciation (IPA)",          # Standard pronunciations, using IPA
    "false friends (cognates)",     # Eng word vs similar word in another language (e.g., 'actually' ≠ 'actualmente')
    "easily confused words",        # Similar‑sounding Eng words with different meanings (e.g., 'accept/except')
    "near-synonyms",                # Words with similar but not identical meaning (e.g., 'say/tell', 'listen/hear')
    "collocation errors",           # Words that don't naturally go together (e.g., 'make a photo' → 'take a photo')
    "prepositional verbs",          # Wrong preposition after a verb (e.g., 'depend of' → 'depend on')
    "confusable adjectives",        # -ed vs -ing (bored/boring), or other adjective pairs
    "confusable adverbs",           # 'hard/hardly', 'late/lately', 'near/nearly'
    "tense mismatches",             # Wrong tense for time expression (e.g., 'I live here since 2020')
    "countable vs uncountable",     # Many/much, few/little, article usage (e.g., 'an information')
    "gerund vs infinitive",         # Verb pattern errors (e.g., 'I enjoy to read')
    "conditional mix-ups",          # First vs second conditional, 'if' + 'will' errors
    "passive vs active",            # Using active when passive is needed (e.g., 'The car repairs now')
    "modal meaning errors",         # Wrong modal for degree of certainty (e.g., 'can' instead of 'might')
    "silent letters",               # Letters not pronounced (e.g., 'doubt', 'island', 'receipt')
    "homophones",                   # Same sound, diff spelling/meaning (e.g., 'there/their/they’re')
    "homographs with stress",       # Same spelling, diff meaning/pronunciation (e.g., 'record' noun vs verb)
    "common spelling errors",       # Frequent misspellings (e.g., 'necessary', 'accommodation')
    "formality mismatches",         # Using informal language in formal contexts (e.g., 'cheers' instead of 'thank you')
    "direct vs polite forms",       # Literal translation of polite requests (e.g., 'Give me water' → 'Could I have water?')
    "literal translation errors",   # Word‑for‑word translations from L1 (e.g., 'I have 20 years' → 'I am 20')
    "key word transformation"
]

BOT_NAME = "Daily English Quiz"


def get_quiz_history():
    """Read quiz history from GitHub Gist.
    
    Returns:
        dict: Quiz history keyed by category
              Returns empty dict if Gist is not configured or unavailable
    """
    if not GITHUB_TOKEN or not QUIZ_GIST_ID:
        return {}
    
    try:
        url = f"https://api.github.com/gists/{QUIZ_GIST_ID}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        content = response.json()["files"]["quiz_history.json"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"[{ts()}] Warning: Could not read quiz history from Gist: {e}")
        return {}


def update_quiz_history(history_data):
    """Write quiz history to GitHub Gist.
    
    Args:
        history_data: Dictionary of quiz history by category
    """
    if not GITHUB_TOKEN or not QUIZ_GIST_ID:
        return
    
    try:
        url = f"https://api.github.com/gists/{QUIZ_GIST_ID}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        payload = {
            "files": {
                "quiz_history.json": {
                    "content": json.dumps(history_data, indent=2)
                }
            }
        }
        response = requests.patch(url, headers=headers, json=payload, timeout=5)
        response.raise_for_status()
    except Exception as e:
        print(f"[{ts()}] Warning: Could not save quiz history to Gist: {e}")


def generate_quiz(category, recent_questions):
    """Generate an English quiz using the Anthropic API.
    
    Args:
        category: Quiz category (e.g., "idioms", "phrasal verbs")
        recent_questions: List of recent questions from this category to avoid repeats
        
    Returns:
        dict: Contains 'problems', 'answers', and 'insight'
        
    Raises:
        json.JSONDecodeError: If response cannot be parsed as JSON
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    # Build context about recent questions if history exists
    history_context = ""
    if recent_questions:
        history_context = (
            "\n\nAvoid repeating these recent questions on this topic:\n"
        )
        for i, question in enumerate(recent_questions[-10:], 1):  # Last 10 sets of questions
            # Truncate long question sets
            q_preview = question[:500] + "..." if len(question) > 500 else question
            history_context += f"{i}. {q_preview}\n"
    
    # Base prompt shared across all categories
    base_prompt = f"""Generate an English quiz suitable for B1-level adult learners.

The quiz should:
- Have exactly 5 questions
- When showing blanks in questions, use (...) to represent blanks to be filled in — NEVER use underscores (__) as they trigger Discord formatting
- Use Discord formatting: *italics* **bold** ***bold italics*** etc. where appropriate
- Never include unescaped double quotes in string values; use single quotes or rephrase instead{history_context}

Only finalize if answers are unambiguous with one defensible correct answer.

Respond in this exact JSON format with no other text:
{{
"problems": "the problem set here",
"answers": "the answers, clearly numbered 1-5",
"insight": "insights or tips related to the theme"
}}"""

    # Category-specific details
    if category == "key word transformation":
        category_prompt = """Generate a B1-C1 Key Word Transformation quiz in JSON format with the following strict rules.

## Format
- Exactly 5 questions.
- Each question has: original sentence, incomplete second sentence with (...) for the gap, a keyword in **bold**.
- 4 multiple-choice options (A-D). Each option is ONLY the words that fill (...), including the keyword exactly as given (same spelling, same tense, no added prefixes/suffixes).
- Each option must be 2-8 words total (count the keyword as one word).
- Provide answers as "1A, 2C, 3B...", and for each correct answer also show the full completed sentence.
- Include a short "insight" about a common transformation error.

## Critical rules to avoid wrong options
1. **Keyword must be identical in every option** - no "been" vs "being", no "would" vs "will", no added 'ed' or 'ing'. If the keyword is "been", all options must contain the exact string "been".
2. **Distractors must be grammatically possible** but change meaning or break a specific rule (e.g., wrong auxiliary, wrong word order, wrong preposition, wrong clause type). Never use nonsense strings.
3. **No ambiguous correct answers** - only one option preserves the original meaning fully. The other three must change meaning in a clear, identifiable way (e.g. tense error, passive/active mismatch, wrong conditional).
4. **Vary correct answer position** - avoid three consecutive questions with the same letter answer.

## Self-check before output
- For each question, verify that every distractor uses the keyword exactly as given (character-by-character match).
- Verify that each distractor is a full, grammatical English phrase (even if wrong for meaning).
- Verify that the correct answer is the only one that keeps the original sentence's tense, modality, and logical meaning.

## Output JSON format
{
"problems": "Question 1:\nOriginal: '...'\nComplete: '... (...) ...'\nKeyword: ...\nA) ...\nB) ...\nC) ...\nD) ...\n\nQuestion 2: ...",
"answers": "1. A - '...' (Full sentence: ...)\n2. C - '...' ...",
"insight": "Tip about a common keyword transformation pitfall at B1 level."
}"""
    else:
        category_prompt = f"""Generate a {category} English quiz.

The quiz should:
- Have a clean, unambiguous problem statement with exactly 5 questions about English {category} or the chosen sub-theme
- Be challenging but doable with reasonable confidence
- Have a specific, unambiguous answer to each question — there must be ONE clearly correct answer
- For each question, ensure no other answer choice is equally valid, grammatically correct, or could be justified by regional/colloquial variants
- Avoid questions where multiple answers could work or where informal/colloquial usage conflicts with the "correct" answer
- Be humorous, interesting, or surprising at times (not required, but appreciated)
- Keep the answers concise and significantly under 1500 characters combined
- If using multiple choice, ensure the correct answers are not all the same letter (vary answer positions)"""

    prompt = base_prompt + "\n\n" + category_prompt
    
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    return parse_json_response(raw)


def main():
    # Step 1: Read quiz history from Gist
    print(f"[{ts()}] Reading quiz history from Gist")
    quiz_history = get_quiz_history()
    
    # Step 2: Generate today's quiz
    category = random.choice(CATEGORIES)
    recent_questions = quiz_history.get(category, [])
    print(f"[{ts()}] Generating {category} quiz (avoiding {len(recent_questions)} sets of recent questions)")
    
    try:
        quiz_data = generate_quiz(category, recent_questions)
    except json.JSONDecodeError as e:
        print(f"[{ts()}] Failed to generate quiz: {e}")
        post_to_discord_safe(
            "⚠️ Daily English Quiz encountered an error generating today's quiz. Please try again later.",
            BOT_NAME,
            DISCORD_WEBHOOK_URL
        )
        return
    except Exception as e:
        print(f"[{ts()}] Unexpected error during quiz generation: {e}")
        post_to_discord_safe(
            "⚠️ Daily English Quiz encountered an unexpected error. Please try again later.",
            BOT_NAME,
            DISCORD_WEBHOOK_URL
        )
        return

    # Step 3: Post today's quiz
    print(f"[{ts()}] Posting today's quiz")
    quiz_message = (
        f"📚 **Daily English Quiz — {category.title()}**\n\n"
        f"{quiz_data['problems']}\n\n"
        f"*Think you know the answers? Share below and check the answers!*"
    )
    
    if not post_to_discord_safe(quiz_message, BOT_NAME, DISCORD_WEBHOOK_URL):
        print(f"[{ts()}] Error: Failed to post quiz (payload too long). Aborting.")
        return

    # Step 4: Post the answers and insight separately from the problems
    print(f"[{ts()}] Posting the answers and insight")
    
    answers = quiz_data.get("answers", "N/A")
    insight = quiz_data.get("insight", "")
    
    # Validate insight length
    if len(insight) > 1500:
        insight = insight[:1500] + "\n*(truncated)*"
    
    answer_message = (
        f"💡 **Answers to the {category.title()} Quiz:**\n\n"
        f"||{answers}||\n\n"
        f"*Please verify the answers with an English helper or native speaker*"
    )
    
    # Append insight if available
    if insight:
        insight_message = (
            f"🤔 **Did You Know?**\n\n"
            f"{insight}"
        )
        # Check combined length before appending
        combined = answer_message + "\n\n" + insight_message
        if len(combined) <= 2000:
            answer_message = combined
        else:
            # Post separately if too long
            if not post_to_discord_safe(answer_message, BOT_NAME, DISCORD_WEBHOOK_URL):
                print(f"[{ts()}] Warning: Failed to post answer message")
            if not post_to_discord_safe(insight_message, BOT_NAME, DISCORD_WEBHOOK_URL):
                print(f"[{ts()}] Warning: Failed to post insight message")
            print(f"[{ts()}] Done!")
            # Save history before returning
            updated_history = recent_questions + [quiz_data['problems']]
            if len(updated_history) > 10:
                updated_history = updated_history[-10:]
            quiz_history[category] = updated_history
            update_quiz_history(quiz_history)
            return
    
    if not post_to_discord_safe(answer_message, BOT_NAME, DISCORD_WEBHOOK_URL):
        print(f"[{ts()}] Warning: Failed to post answer and insight message")
    
    # Step 5: Save quiz history to Gist
    print(f"[{ts()}] Saving quiz history to Gist")
    updated_history = recent_questions + [quiz_data['problems']]
    if len(updated_history) > 10:
        updated_history = updated_history[-10:]
    quiz_history[category] = updated_history
    update_quiz_history(quiz_history)
    
    print(f"[{ts()}] Done!")


if __name__ == "__main__":
    main()