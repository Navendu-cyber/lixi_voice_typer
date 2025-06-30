import speech_recognition as sr
from pynput.keyboard import Controller, Key
import subprocess
import time
import os
import google.generativeai as genai # New: For direct Gemini API interaction
import pvporcupine # For hotword detection
import sounddevice as sd # For pvporcupine audio input
import numpy as np # For pvporcupine audio processing

# --- Configuration ---
AWAKE_SOUND_FILE = "gemini_awake.wav" # Ensure this file is in the same directory as this script
# For Hotword Detection (pvporcupine)
HOTWORD_ENABLED = False # Set to True if you want to use a wake word (e.g., "Lixi")
# You NEED to replace 'YOUR_PICOVOICE_ACCESS_KEY' with your actual key from Picovoice Console
PICOVOICE_ACCESS_KEY = "YOUR_PICOVOICE_ACCESS_KEY"
# You NEED to replace 'path/to/your/gemini_linux.ppn' with the actual path to your .ppn file
# Download from Picovoice Console, often found within their SDK in resources/keyword_files/linux/
KEYWORD_FILE_PATH = "path/to/your/gemini_linux.ppn"
HOTWORD = "lixi" # Your desired wake word (lowercase). Make sure you download/generate a .ppn file for this word.

# For Google Gemini API interaction
# You NEED to replace 'YOUR_GEMINI_API_KEY' with your actual API key from Google AI Studio
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"

# --- Initialize Components ---
recognizer = sr.Recognizer()
keyboard = Controller()

# Configure Gemini API
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    # Start a chat session for multi-turn conversations
    chat = model.start_chat(history=[])
    print("Gemini API configured successfully.")
except Exception as e:
    print(f"Error configuring Gemini API: {e}")
    print("Please ensure your GEMINI_API_KEY is correct and has access to Gemini Pro.")
    model = None # Set model to None if configuration failed

def play_sound(file_path):
    """Plays a sound file using paplay (Kubuntu's default for PulseAudio)."""
    if not os.path.exists(file_path):
        print(f"Warning: Sound file not found at {file_path}. Skipping playback.")
        return

    try:
        # `paplay` is robust for .wav and .ogg on PulseAudio systems
        subprocess.run(["paplay", file_path], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"Error playing sound: {e.stderr.decode().strip()}")
        print("Ensure 'paplay' is installed (sudo apt install pulseaudio-utils) and the sound file path is correct.")
    except FileNotFoundError:
        print("Error: 'paplay' command not found. Please install it: sudo apt install pulseaudio-utils")
    except Exception as e:
        print(f"An unexpected error occurred during sound playback: {e}")

def speak_response(text):
    """Uses spd-say to speak the given text."""
    print(f"Assistant speaking: {text}")
    try:
        # `spd-say` is a good default for speaking text on Linux
        subprocess.run(["spd-say", text], check=True)
    except FileNotFoundError:
        print("Warning: 'spd-say' not found. Install with: sudo apt install speech-dispatcher. Cannot speak response.")
    except subprocess.CalledProcessError as e:
        print(f"Error during TTS (spd-say): {e.stderr.decode().strip()}")
    except Exception as e:
        print(f"An unexpected error occurred during TTS: {e}")

def get_speech_input():
    """Listens for speech and converts it to text."""
    with sr.Microphone() as source:
        print("Listening for your command...")
        recognizer.adjust_for_ambient_noise(source, duration=0.8) # Adjust for noise
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=10) # Listen for up to 10 seconds

        try:
            # Use Google Web Speech API for recognition (requires internet)
            text = recognizer.recognize_google(audio)
            print(f"You said: '{text}'")
            return text
        except sr.UnknownValueError:
            print("Sorry, I could not understand the audio.")
            return None
        except sr.WaitTimeoutError:
            print("No speech detected within the timeout period.")
            return None
        except sr.RequestError as e:
            print(f"Could not request results from Google Speech Recognition service; {e}")
            print("Please check your internet connection and API quotas.")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during speech recognition: {e}")
            return None

def process_command(command_text):
    """Processes the recognized command and interacts with Gemini."""
    if not command_text:
        return

    command_text_lower = command_text.lower().strip()

    if command_text_lower in ["exit", "goodbye", "quit assistant"]:
        speak_response("Goodbye! Have a great day.")
        return "exit_app" # Signal to exit the main loop

    if command_text_lower.startswith("open "):
        app_name = command_text_lower[len("open "):].strip()
        print(f"Attempting to open: {app_name}")
        speak_response(f"Opening {app_name}.")
        try:
            # Use xdg-open for general files/apps or direct command for specific apps
            if app_name == "browser":
                subprocess.Popen(["xdg-open", "https://www.google.com"])
            elif app_name == "terminal" or app_name == "konsole":
                subprocess.Popen(["konsole"])
            elif app_name == "file manager" or app_name == "dolphin":
                subprocess.Popen(["dolphin"])
            elif app_name == "vs code" or app_name == "vscode":
                subprocess.Popen(["code"]) # Assumes 'code' command is in PATH
            else:
                subprocess.Popen([app_name]) # Try to run it directly
        except FileNotFoundError:
            speak_response(f"Sorry, I couldn't find '{app_name}' on your system.")
        except Exception as e:
            speak_response(f"An error occurred trying to open {app_name}.")
            print(f"Error opening app: {e}")
        return

    if command_text_lower.startswith("run "):
        shell_command = command_text_lower[len("run "):].strip()
        print(f"Executing shell command: {shell_command}")
        speak_response(f"Executing {shell_command}.")
        try:
            # Use subprocess.run for commands you want to wait for or capture output
            # For background processes, use subprocess.Popen
            result = subprocess.run(shell_command, shell=True, check=False, capture_output=True, text=True)
            if result.stdout:
                print(f"Command output:\n{result.stdout}")
                speak_response("Command executed. Check the terminal for output.")
            if result.stderr:
                print(f"Command error:\n{result.stderr}")
                speak_response("Command executed with errors. Check the terminal for details.")
        except Exception as e:
            speak_response(f"An error occurred while trying to run the command.")
            print(f"Error running command: {e}")
        return

    # Default: Send command to Gemini API
    if model:
        try:
            print("Sending command to Gemini API...")
            speak_response("Thinking...")
            # Send the message to the chat session
            response = chat.send_message(command_text)
            gemini_reply = response.text
            print(f"Gemini: {gemini_reply}")
            speak_response(gemini_reply)
        except Exception as e:
            speak_response("Sorry, I couldn't connect to Gemini or there was an API error.")
            print(f"Gemini API Error: {e}")
    else:
        speak_response("Gemini API is not configured. I can only handle local commands.")

# --- Main Voice Assistant Loop ---
def start_lixi_assistant():
    print("\n--- Lixi Voice Assistant Started ---")
    if HOTWORD_ENABLED:
        global porcupine # Declare global to clean up later
        global hotword_detected # Flag to signal detection

        hotword_detected = False
        try:
            # Check for Porcupine AccessKey and Keyword Path
            if PICOVOICE_ACCESS_KEY == "YOUR_PICOVOICE_ACCESS_KEY":
                print("ERROR: Picovoice AccessKey not set. Hotword detection will not work.")
                HOTWORD_ENABLED = False
            elif not os.path.exists(KEYWORD_FILE_PATH):
                print(f"ERROR: Hotword keyword file not found at {KEYWORD_FILE_PATH}. Hotword detection will not work.")
                HOTWORD_ENABLED = False

            if HOTWORD_ENABLED:
                porcupine = pvporcupine.create(
                    access_key=PICOVOICE_ACCESS_KEY,
                    keyword_paths=[KEYWORD_FILE_PATH]
                )
                print(f"Listening for wake word '{HOTWORD}'...")
                speak_response(f"Hello, I am Lixi. Waiting for {HOTWORD}.")

                def hotword_callback(indata, frames, time_info, status):
                    nonlocal hotword_detected # For Python 3.x, use nonlocal for outer scope variable
                    if status:
                        print(status)
                    pcm = indata.flatten().astype(np.int16)
                    result = porcupine.process(pcm)
                    if result >= 0:
                        print(f"Wake word '{HOTWORD}' detected!")
                        hotword_detected = True

                with sd.InputStream(
                    channels=1,
                    samplerate=porcupine.sample_rate,
                    blocksize=porcupine.frame_length,
                    callback=hotword_callback
                ):
                    while True:
                        if hotword_detected:
                            play_sound(AWAKE_SOUND_FILE)
                            speak_response("Yes?")
                            command = get_speech_input()
                            if process_command(command) == "exit_app":
                                break
                            hotword_detected = False # Reset for next detection
                            speak_response(f"Waiting for {HOTWORD}.")
                        time.sleep(0.1) # Small delay to prevent busy-waiting

        except pvporcupine.PorcupineError as e:
            print(f"Porcupine error: {e}")
            print("Ensure your Picovoice AccessKey and keyword file path are correct for hotword.")
            HOTWORD_ENABLED = False # Disable hotword if error
        except Exception as e:
            print(f"An unexpected error occurred in hotword detection: {e}")
            HOTWORD_ENABLED = False # Disable hotword if error
        finally:
            if 'porcupine' in locals() and porcupine is not None:
                porcupine.delete()

    # If hotword is not enabled, or if it failed to start, run in single-command mode
    if not HOTWORD_ENABLED:
        print("Running in single-command mode (triggered by shortcut).")
        play_sound(AWAKE_SOUND_FILE)
        speak_response("Yes?")
        command = get_speech_input()
        process_command(command)
        # In shortcut mode, the script exits after one command,
        # so the shortcut needs to be pressed again for the next command.
        # To make it truly continuous in shortcut mode, you'd need to loop this
        # and manage the Konsole input focus carefully, which is harder.
        # The hotword method is better for continuous hands-free operation.

    print("--- Lixi Voice Assistant Finished ---")


if __name__ == "__main__":
    # Ensure 'paplay' and 'spd-say' are installed if you want sound/speech feedback
    # You can install them: sudo apt install pulseaudio-utils speech-dispatcher

    # Install google-generativeai library if not already installed (for direct API interaction)
    try:
        import google.generativeai
    except ImportError:
        print("Installing google-generativeai library...")
        subprocess.run(["pip", "install", "google-generativeai"], check=True)
        print("google-generativeai installed. Please restart the script.")
        exit() # Exit to allow the new import to take effect

    start_lixi_assistant()