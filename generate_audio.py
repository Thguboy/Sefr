import os

def create_placeholder():
    # A tiny silent WAV file (valid header)
    # Browsers often play WAV even if extension is .mp3
    wav_header = (
        b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>'
        b'\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
    )
    
    target_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "audio")
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    
    file_path = os.path.join(target_dir, "placeholder.mp3")
    with open(file_path, "wb") as f:
        f.write(wav_header)
    print(f"Created {file_path}")

if __name__ == "__main__":
    create_placeholder()
