# !pip install -q accelerate==0.21.0 peft==0.4.0 bitsandbytes==0.40.2 transformers==4.31.0 trl==0.4.7

import os
import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    HfArgumentParser,
    TrainingArguments,
    pipeline,
    logging,
)
from peft import LoraConfig, PeftModel, get_peft_model
from trl import SFTTrainer

from generate_mapping_dataset import D_KV_SUBS, D_KV_VAL, D_SUBS_VAL, create_arithmetic_expressions

import pandas as pd
df = pd.DataFrame(D_KV_SUBS)

from datasets import Dataset
dataset = Dataset.from_pandas(df.rename(columns={0: "text"}), split="train")

print("Dataset loaded successfully. \n")

# The model that you want to train from the Hugging Face hub
model_name = "meta-llama/Llama-2-7b-chat-hf"

################################################################################
# bitsandbytes parameters
################################################################################

# Activate 4-bit precision base model loading
use_4bit = True

# Compute dtype for 4-bit base models
bnb_4bit_compute_dtype = "float16"

# Quantization type (fp4 or nf4)
bnb_4bit_quant_type = "nf4"

# Activate nested quantization for 4-bit base models (double quantization)
use_nested_quant = False

################################################################################
# TrainingArguments parameters
################################################################################

# Output directory where the model predictions and checkpoints will be stored
output_dir = "./results"

# Number of training epochs
num_train_epochs = 1

# Enable fp16/bf16 training (set bf16 to True with an A100)
fp16 = False
bf16 = False

# Batch size per GPU for training
per_device_train_batch_size = 64

# Batch size per GPU for evaluation
per_device_eval_batch_size = 16

# Number of update steps to accumulate the gradients for
gradient_accumulation_steps = 1

# Enable gradient checkpointing
gradient_checkpointing = True

# Maximum gradient normal (gradient clipping)
max_grad_norm = 0.3

# Initial learning rate (AdamW optimizer)
learning_rate = 2e-4

# Weight decay to apply to all layers except bias/LayerNorm weights
weight_decay = 0.001

# Optimizer to use
optim = "paged_adamw_32bit"

# Learning rate schedule
lr_scheduler_type = "cosine"

# Number of training steps (overrides num_train_epochs)
max_steps = -1

# Ratio of steps for a linear warmup (from 0 to learning rate)
warmup_ratio = 0.03

# Group sequences into batches with same length
# Saves memory and speeds up training considerably
group_by_length = True

# Save checkpoint every X updates steps
save_steps = 0

# Log every X updates steps
logging_steps = 25

################################################################################
# SFT parameters
################################################################################

# Maximum sequence length to use
max_seq_length = None

# Pack multiple short examples in the same input sequence to increase efficiency
packing = False

# Load the entire model on the GPU 0
device_map = {"": 0}

# Load tokenizer and model with QLoRA configuration
compute_dtype = getattr(torch, bnb_4bit_compute_dtype)

bnb_config = BitsAndBytesConfig(
    load_in_4bit=use_4bit,
    bnb_4bit_quant_type=bnb_4bit_quant_type,
    bnb_4bit_compute_dtype=compute_dtype,
    bnb_4bit_use_double_quant=use_nested_quant,
)

# Check GPU compatibility with bfloat16
if compute_dtype == torch.float16 and use_4bit:
    major, _ = torch.cuda.get_device_capability()
    if major >= 8:
        print("=" * 80)
        print("Your GPU supports bfloat16: accelerate training with bf16=True")
        print("=" * 80)

# Load base model
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=bnb_config,
    device_map=device_map
)
model.config.use_cache = False
model.config.pretraining_tp = 1

# Load LLaMA tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right" # Fix weird overflow issue with fp16 training

peft_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q_proj", "k_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

# Set training parameters
# training_arguments = TrainingArguments(
#     # use_cpu = True,
#     output_dir=output_dir,
#     num_train_epochs=num_train_epochs,
#     per_device_train_batch_size=per_device_train_batch_size,
#     gradient_accumulation_steps=gradient_accumulation_steps,
#     optim=optim,
#     save_steps=save_steps,
#     logging_steps=logging_steps,
#     learning_rate=learning_rate,
#     weight_decay=weight_decay,
#     fp16=fp16,
#     bf16=bf16,
#     max_grad_norm=max_grad_norm,
#     max_steps=max_steps,
#     warmup_ratio=warmup_ratio,
#     group_by_length=group_by_length,
#     lr_scheduler_type=lr_scheduler_type,
#     report_to="tensorboard"
# )

model = get_peft_model(model, peft_config)

import transformers

trainer = transformers.Trainer(
    model=model,
    train_dataset=dataset["text"],
    args=transformers.TrainingArguments( 
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_steps=100,
        max_steps=100,
        learning_rate=1e-3,
        fp16=True,
        logging_steps=1,
        output_dir='outputs',
        # use_cpu=False,
        # push_to_hub=True,
    ),
    data_collator=transformers.DataCollatorForLanguageModeling(tokenizer, mlm=False)
)
# Train model
trainer.train()

# Save trained model
trainer.model.save_pretrained(new_model)

# %load_ext tensorboard
# %tensorboard --logdir results/runs

# Ignore warnings
logging.set_verbosity(logging.CRITICAL)

# Run text generation pipeline with our next model
# prompt = "What is a large language model?"
prompt, expected_ans, _ = create_arithmetic_expressions()
pipe = pipeline(task="text-generation", model=model, tokenizer=tokenizer, max_length=200)
result = pipe(f"<s>[INST] Given an arithmetic expression between strings: {prompt}. Find the corresponding arithmetic expression in numeric terms between the numeric mappings of those strings.[/INST]")
print(result[0]['generated_text'])

# Empty VRAM
# import gc
# gc.collect()
# gc.collect()

# Reload model in FP16 and merge it with LoRA weights
# base_model = AutoModelForCausalLM.from_pretrained(
#     model_name,
#     low_cpu_mem_usage=True,
#     return_dict=True,
#     torch_dtype=torch.float16,
#     device_map=device_map,
# )
# model = PeftModel.from_pretrained(base_model, new_model)
# model = model.merge_and_unload()

# # Reload tokenizer to save it
# tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
# tokenizer.pad_token = tokenizer.eos_token
# tokenizer.padding_side = "right"

# !huggingface-cli login
access_token = "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"
model.push_to_hub("llama-2-7b-lora-key-value-mappings", token = access_token)

# model.push_to_hub(new_model, use_temp_dir=False)
# tokenizer.push_to_hub(new_model, use_temp_dir=False)
