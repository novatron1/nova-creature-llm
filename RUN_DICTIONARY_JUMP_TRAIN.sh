#!/bin/bash
# Dictionary Brain Jump - Offline Training Runner
# Run this on a machine with PyTorch installed

echo "=== Dictionary Brain Jump: Offline Training ==="
echo ""

# Install PyTorch if needed
python3 -c "import torch" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing PyTorch (CPU)..."
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
fi

echo "Training transformers with dictionary knowledge..."
python3 -c "
import sys
sys.path.insert(0, 'src')
from v055_assisted_learning_bridge import run_finetune, get_queue_size, get_checkpoint_hashes

# Record before
before = get_checkpoint_hashes()
print('Before training:')
for k, v in sorted(before.items()):
    print(f'  {k}: {v[:20]}...')

# Run training
qsize = get_queue_size()
print(f'\nLessons queued: {qsize}')
print('Training...')
result = run_finetune()

# Record after
after = get_checkpoint_hashes()
print('\nAfter training:')
changes = 0
for k, v in sorted(after.items()):
    b = before.get(k, '')
    changed = 'CHANGED' if b != v else 'SAME'
    if b != v: changes += 1
    print(f'  {k}: {v[:20]}... ({changed})')

print(f'\nTotal weight changes: {changes}')
print('Training complete!')
"
