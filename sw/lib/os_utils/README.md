To install the rust compiler (needed for the cryptography library), you can use the following command:

```bash
apt update
apt install build-essential curl ca-certificates -y
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
```

then run pip install cryptography. If you are using a virtual environment, make sure to activate it before running the pip install command.