# Nova Mini LLM

This is a real, small Transformer language model using the same core technology shown in your picture:
embeddings, positional encoding, masked multi-head attention, feed-forward layers, residual connections,
layer normalization, and softmax prediction.

It is not ChatGPT-scale. It is a tiny LLM you can train on your own text file.

## What it does

- Reads a text file
- Learns patterns from the text
- Predicts the next character/token
- Generates new text one piece at a time
- Saves a trained model checkpoint

## Files

- `model.py` — Transformer/GPT model
- `train.py` — trains the model
- `generate.py` — generates text from a saved model
- `data.txt` — small starter training text
- `requirements.txt` — install requirements

## Setup

```bash
pip install -r requirements.txt
```

## Train

```bash
python train.py --data data.txt --steps 1000
```

For a faster test:

```bash
python train.py --data data.txt --steps 200
```

## Generate

```bash
python generate.py --prompt "Once upon a time" --max_new_tokens 300
```

## How to train it on your own text

Replace `data.txt` with your own writing, lyrics, scripts, stories, notes, or documents converted to plain text.

The more text you give it, the better it learns your style.

## Simple explanation

This model looks at the letters before the next letter and learns:

> Based on what came before, what probably comes next?

Then it repeats that many times to create new text.
