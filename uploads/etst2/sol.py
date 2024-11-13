import torch
import time

a1 = time.time()

names = open('names.txt').read().split('\n')
chars = {'.': 0}
set_chars = set()

for name in names:
    for char in name.lower():
        set_chars.add(char)

for i, letter in enumerate(sorted(list(set_chars))):
    chars[letter] = i + 1

keys_chars = list(chars.keys())
N = torch.zeros((27, 27), dtype=torch.int64)

for name in names:
    name = name.lower()
    sequence = ['.'] + list(name) + ['.']
    for ch1, ch2 in zip(sequence, sequence[1:]):
        N[chars[ch1], chars[ch2]] += 1

frequency_dict = {
    f"{keys_chars[i]}{keys_chars[j]}": N[i, j].item()
    for i in range(27)
    for j in range(27)
    if N[i, j] > 0
}

a2 = time.time()
print(a2-a1)

print(frequency_dict["a."])
