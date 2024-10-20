import streamlit as st
import boto3
import openai
import moviepy.editor as mp
import time
import requests


# Set up OpenAI and AWS credentials (use environment variables)
openai.api_type = "azure"
openai.api_key = "c1689c3d23854ba18b7a1fad31c9b1ad"  # Set your Azure OpenAI API key
openai.api_base = "https://deku-extremes.openai.azure.com/"
openai.api_version = "2024-08-01-preview"
# Streamlit UI
st.title("AI-Powered Video Audio Replacement")
st.write("Upload a video file, and we'll transcribe the audio, correct it, and replace the original audio with an AI-generated voice.")

# Upload video file
uploaded_video = st.file_uploader("Upload a Video File", type=["mp4", "mov", "avi"])

if uploaded_video is not None:
    # Save the uploaded video temporarily
    video_path = "uploaded_video.mp4"
    with open(video_path, "wb") as f:
        f.write(uploaded_video.read())

    # Extract audio from the video
    st.info("Extracting audio from the video...")
    video_clip = mp.VideoFileClip(video_path)
    audio_path = "extracted_audio.wav"
    video_clip.audio.write_audiofile(audio_path)

    # AWS S3: Upload extracted audio to S3
    s3_client = boto3.client('s3')
    bucket_name = "my-aws-bucketz"  # Replace with your S3 bucket name
    s3_audio_path = f"s3://{bucket_name}/{audio_path}"

    def upload_audio_to_s3(file_name, bucket, object_name=None):
        if object_name is None:
            object_name = file_name
        try:
            s3_client.upload_file(file_name, bucket, object_name)
            st.success(f"Uploaded {file_name} to S3 bucket {bucket}.")
        except Exception as e:
            st.error(f"Error uploading {file_name} to S3: {e}")

    # Upload audio to S3
    upload_audio_to_s3(audio_path, bucket_name)

    # AWS Transcribe: Transcribing audio to text
    st.info("Transcribing audio using Amazon Transcribe...")
    transcribe_client = boto3.client('transcribe')

    job_name = "transcribe_job_1"
    job_uri = f"https://s3.amazonaws.com/{bucket_name}/{audio_path}"

    def start_transcription_job(job_name, job_uri):
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': job_uri},
            MediaFormat='wav',
            LanguageCode='en-US'
        )

    def get_transcription_result(job_name):
        while True:
            status = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
            if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
                break
            st.write("Transcription in progress...")
            time.sleep(30)
        return status['TranscriptionJob']['Transcript']['TranscriptFileUri']

    # Start the transcription job and retrieve the result
    start_transcription_job(job_name, job_uri)
    transcription_uri = get_transcription_result(job_name)

    # Fetch transcription text from the transcription URI
    transcription_uri = get_transcription_result(job_name)
    response = requests.get(transcription_uri)
    transcription_json = response.json()
    transcription_text = transcription_json['results']['transcripts'][0]['transcript']


    # Display the original transcription
    st.write("Original Transcription:")
    st.text_area("Original Transcription:", transcription_text)

    # Correct transcription using OpenAI GPT
    st.info("Correcting transcription with GPT-4z...")
    def correct_transcription(text):
        try:
            response = openai.ChatCompletion.create(
                engine="gpt-35-turbo",  # Azure OpenAI deployment ID
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that corrects transcripts by removing filler words and fixing grammatical errors and just give the corrected transcript without adding anything before"},
                    {"role": "user", "content": f"Correct the following transcript: {text}"}
                ],
                max_tokens=1000,  # Adjust token limit as needed
                temperature=0.5 
                )
    # Return the corrected transcription from the response
            return response.choices[0].message["content"].strip()
        except openai.error.RateLimitError:
            st.warning("Rate limit exceeded. Retrying after a delay...")
            time.sleep(60 * 60 * 24)  # Retry after 24 hours
            return correct_transcription(text)

    corrected_transcript = correct_transcription(transcription_text)
    st.text_area("Corrected Transcription:", corrected_transcript)

    # AWS Polly: Convert corrected text to speech
    st.info("Generating new audio using Amazon Polly...")
    polly_client = boto3.client('polly')

    def generate_speech(text, output_audio_file="new_audio.mp3"):
        response = polly_client.synthesize_speech(
            VoiceId='Matthew',  # You can change the voice as needed
            OutputFormat='mp3',
            Text=text
        )
        with open(output_audio_file, "wb") as file:
            file.write(response['AudioStream'].read())
        return output_audio_file

    new_audio_file = generate_speech(corrected_transcript)
    st.audio(new_audio_file)

    # Replace original video audio with new AI-generated audio
    st.info("Replacing original audio in the video...")

    def replace_audio_in_video(video_file, new_audio_file, output_file):
        video_clip = mp.VideoFileClip(video_file)
        new_audio = mp.AudioFileClip(new_audio_file)
        final_video = video_clip.set_audio(new_audio)
        final_video.write_videofile(output_file)

    final_video_output = "final_video_with_ai_audio.mp4"
    replace_audio_in_video(video_path, new_audio_file, final_video_output)

    st.video(final_video_output)

st.write("Process completed.")
