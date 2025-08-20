const chatWindow = document.getElementById('chat-window');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');

function appendMessage(text, who='bot'){
  const div = document.createElement('div');
  div.className = `msg ${who}`;
  div.textContent = text;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function sendMessage(){
  const text = userInput.value.trim();
  if(!text){ return; }
  appendMessage(text, 'user');
  userInput.value='';
  try{
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    });
    const data = await res.json();
    appendMessage(data.reply, 'bot');
  }catch(e){
    appendMessage('Network error. Please try again.', 'bot');
  }
}

sendBtn?.addEventListener('click', sendMessage);
userInput?.addEventListener('keydown', (e)=>{
  if(e.key === 'Enter'){ sendMessage(); }
});
