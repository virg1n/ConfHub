first_letter = input()
second_letter = input()

# Attempt to read names from 'names.txt'
try:
    with open('names.txt', 'r', encoding='utf-8') as file:
        names = file.read().splitlines()
except FileNotFoundError:
    print("Error: 'names.txt' file not found. Please check the file path.")
    exit()

# Display first few names to check if file was read correctly
# print("Sample names from the dataset:", names[:5])

chars = {'.': 0}
set_chars = set()

for name in names:
    for char in name.lower():
        set_chars.add(char)

# Map each character to an index in the 27x27 matrix
for i, letter in enumerate(sorted(list(set_chars))):
    chars[letter] = i + 1

keys_chars = ['.'] + sorted(list(set_chars))

# Initialize a 27x27 matrix to count letter pairs
N = [[0 for _ in range(27)] for _ in range(27)]

# Populate the frequency matrix
for name in names:
    name = name.lower()
    sequence = ['.'] + list(name) + ['.']
    for ch1, ch2 in zip(sequence, sequence[1:]):
        if ch1 in chars and ch2 in chars:
            N[chars[ch1]][chars[ch2]] += 1

# Build frequency dictionary from non-zero matrix counts
frequency_dict = {
    f"{keys_chars[i]}{keys_chars[j]}": N[i][j]
    for i in range(27)
    for j in range(27)
    if N[i][j] > 0
}

# Print the frequency of the specified letter pair, or 0 if it does not exist
pair_key = str(first_letter + second_letter)
print(frequency_dict.get(pair_key, 0))
