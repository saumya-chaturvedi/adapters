# -*- coding: utf-8 -*-
"""Llama LoRA Implementation.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1fT7Vi4XsPN43DicK4gqScpK8kCbD7NVm

# Simplified LoRA Implementation

#### Install Dependencies
"""

#!pip install -q bitsandbytes datasets accelerate loralib
#!pip install -q git+https://github.com/huggingface/peft.git git+https://github.com/huggingface/transformers.git

"""#### Confirm CUDA"""

import torch
print(torch.cuda.is_available())

"""#### Load Base Model"""

import os
os.environ["CUDA_VISIBLE_DEVICES"]="0"
import torch
import torch.nn as nn
import bitsandbytes as bnb
from transformers import AutoTokenizer, AutoConfig, AutoModelForCausalLM

tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-2-7b-chat-hf")
model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-2-7b-chat-hf")

"tokenizer.pad_token = tokenizer.eos_token

## cuda summary 

import sys
from subprocess import call
print('_____Python, Pytorch, Cuda info____')
print('__Python VERSION:', sys.version)
print('__pyTorch VERSION:', torch.__version__)
print('__CUDA RUNTIME API VERSION')
#os.system('nvcc --version')
print('__CUDNN VERSION:', torch.backends.cudnn.version())
print('_____nvidia-smi GPU details____')
call(["nvidia-smi", "--format=csv", "--query-gpu=index,name,driver_version,memory.total,memory.used,memory.free"])
print('_____Device assignments____')
print('Number CUDA Devices:', torch.cuda.device_count())
print ('Current cuda device: ', torch.cuda.current_device(), ' **May not correspond to nvidia-smi ID above, check visibility parameter')
print("Device name: ", torch.cuda.get_device_name(torch.cuda.current_device()))


"""##### View Model Summary"""

print(model)

for param in model.parameters():
  param.requires_grad = False  # freeze the model - train adapters later
  if param.ndim == 1:
    # cast the small parameters (e.g. layernorm) to fp32 for stability
    param.data = param.data.to(torch.float32)

model.gradient_checkpointing_enable()  # reduce number of stored activations
model.enable_input_require_grads()

class CastOutputToFloat(nn.Sequential):
  def forward(self, x): return super().forward(x).to(torch.float32)
model.lm_head = CastOutputToFloat(model.lm_head)

"""#### Helper Function"""

def print_trainable_parameters(model):
    """
    Prints the number of trainable parameters in the model.
    """
    trainable_params = 0
    all_param = 0
    for _, param in model.named_parameters():
        all_param += param.numel()
        if param.requires_grad:
            trainable_params += param.numel()
    print(
        f"trainable params: {trainable_params} || all params: {all_param} || trainable%: {100 * trainable_params / all_param}"
    )

"""#### Obtain LoRA Model"""

from peft import LoraConfig, get_peft_model

config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q_proj", "k_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, config)
print_trainable_parameters(model)

"""#### Load Sample Dataset"""

import datasets
from datasets import load_dataset
datasets.builder.has_sufficient_disk_space = lambda needed_bytes, directory='.': True
qa_dataset = load_dataset("squad_v2")

"""```
### CONTEXT
{context}

### QUESTION
{question}

### ANSWER
{answer}</s>
```
"""

def create_prompt(context, question, answer):
  if len(answer["text"]) < 1:
    answer = "Cannot Find Answer"
  else:
    answer = answer["text"][0]
  prompt_template = f"### CONTEXT\n{context}\n\n### QUESTION\n{question}\n\n### ANSWER\n{answer}</s>"
  return prompt_template

mapped_qa_dataset = qa_dataset.map(lambda samples: tokenizer(create_prompt(samples['context'], samples['question'], samples['answers'])))

"""#### Train LoRA"""

import transformers

trainer = transformers.Trainer(
    model=model,
    train_dataset=mapped_qa_dataset["train"],
    args=transformers.TrainingArguments(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_steps=100,
        max_steps=100,
        learning_rate=1e-3,
        fp16=True,
        logging_steps=1,
        output_dir='outputs',
        use_cpu=True,
    ),
    data_collator=transformers.DataCollatorForLanguageModeling(tokenizer, mlm=False)
)
model.config.use_cache = False  # silence the warnings. Please re-enable for inference!
trainer.train()

# HUGGING_FACE_USER_NAME = ""

# from huggingface_hub import notebook_login
# notebook_login()

# model_name = ""

# model.push_to_hub(f"{HUGGING_FACE_USER_NAME}/{model_name}", use_auth_token=True)

# import torch
# from peft import PeftModel, PeftConfig
# from transformers import AutoModelForCausalLM, AutoTokenizer

# peft_model_id = f"{HUGGING_FACE_USER_NAME}/{model_name}"
# config = PeftConfig.from_pretrained(peft_model_id)
# model = AutoModelForCausalLM.from_pretrained(config.base_model_name_or_path, return_dict=True, load_in_8bit=False, device_map='auto')
# tokenizer = AutoTokenizer.from_pretrained(config.base_model_name_or_path)

# # Load the Lora model
# qa_model = PeftModel.from_pretrained(model, peft_model_id)

# from IPython.display import display, Markdown

# def make_inference(context, question):
#   batch = tokenizer(f"### CONTEXT\n{context}\n\n### QUESTION\n{question}\n\n### ANSWER\n", return_tensors='pt')

#   with torch.cuda.amp.autocast():
#     output_tokens = qa_model.generate(**batch, max_new_tokens=200)

#   display(Markdown((tokenizer.decode(output_tokens[0], skip_special_tokens=True))))

# context = "Cheese is the best food."
# question = "What is the best food?"

# make_inference(context, question)

# context = "Cheese is the best food."
# question = "How far away is the Moon from the Earth?"

# make_inference(context, question)

# context = "The Moon orbits Earth at an average distance of 384,400 km (238,900 mi), or about 30 times Earth's diameter. Its gravitational influence is the main driver of Earth's tides and very slowly lengthens Earth's day. The Moon's orbit around Earth has a sidereal period of 27.3 days. During each synodic period of 29.5 days, the amount of visible surface illuminated by the Sun varies from none up to 100%, resulting in lunar phases that form the basis for the months of a lunar calendar. The Moon is tidally locked to Earth, which means that the length of a full rotation of the Moon on its own axis causes its same side (the near side) to always face Earth, and the somewhat longer lunar day is the same as the synodic period. However, 59% of the total lunar surface can be seen from Earth through cyclical shifts in perspective known as libration."
# question = "At what distance does the Moon orbit the Earth?"

# make_inference(context, question)

# marketmail_model = PeftModel.from_pretrained(model, "c-s-ale/bloom-7b1-marketmail-ai")

# from IPython.display import display, Markdown

# def make_inference_mm_ai(product, description):
#   batch = tokenizer(f"Below is a product and description, please write a marketing email for this product.\n\n### Product:\n{product}\n### Description:\n{description}\n\n### Marketing Email:\n", return_tensors='pt')

#   with torch.cuda.amp.autocast():
#     output_tokens = marketmail_model.generate(**batch, max_new_tokens=200)

#   display(Markdown((tokenizer.decode(output_tokens[0], skip_special_tokens=True))))

# your_product_name_here = "The Coolinator"
# your_product_description_here = "A personal cooling device to keep you from getting overheated on a hot summer's day!"

# make_inference_mm_ai(your_product_name_here, your_product_description_here)
