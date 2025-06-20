#!/usr/bin/env python3
import json
import proxai as px
import concurrent.futures
import time
import random
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

chat_history = []
available_models = []

def log_message(level, message, details=None):
    """Pretty logging with timestamps and formatting"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Color codes for different log levels
    colors = {
        'INFO': '\033[94m',    # Blue
        'SUCCESS': '\033[92m', # Green
        'WARNING': '\033[93m', # Yellow
        'ERROR': '\033[91m',   # Red
        'RESET': '\033[0m'     # Reset
    }
    
    color = colors.get(level, colors['RESET'])
    reset = colors['RESET']
    
    # Create the main log line
    log_line = f"{color}[{timestamp}] {level:8} | {message}{reset}"
    print(log_line)
    
    # Add details if provided
    if details:
        if isinstance(details, dict):
            for key, value in details.items():
                print(f"         {color}├─{reset} {key}: {value}")
        elif isinstance(details, list):
            for item in details:
                print(f"         {color}├─{reset} {item}")
        else:
            print(f"         {color}└─{reset} {details}")
    
    print()  # Empty line for readability

def get_largest_models():
    """Get the largest models from each provider, excluding deepseek-r1"""
    log_message('INFO', '🔍 Loading available AI models...')
    
    try:
        largest_models = px.models.list_models(model_size='largest')
        log_message('SUCCESS', f'✅ Retrieved {len(largest_models)} models from ProxAI')

        selected_models = []
        filtered_count = 0
        
        for model in largest_models:
            provider = model.provider
            model_name = model.model

            # Skip deepseek-r1, prefer deepseek-v3
            if provider == 'deepseek' and model_name == 'deepseek-r1':
                filtered_count += 1
                log_message('INFO', f'⚠️  Skipping {provider}/{model_name} (filtered out)')
                continue

            selected_models.append({
                'provider': provider,
                'model': model_name,
                'display_name': f"{provider.title()} {model_name.replace('-', ' ').title()}"
            })
            log_message('INFO', f'✅ Added model: {provider}/{model_name}')

        # Add deepseek-v3 if deepseek is available but we filtered out r1
        if any(m['provider'] == 'deepseek' for m in selected_models) == False:
            try:
                log_message('INFO', '🔍 Checking for deepseek-v3 alternative...')
                all_models = px.models.list_models()
                deepseek_v3 = next((m for m in all_models if m.provider == 'deepseek' and m.model == 'deepseek-v3'), None)
                if deepseek_v3:
                    selected_models.append({
                        'provider': 'deepseek',
                        'model': 'deepseek-v3',
                        'display_name': 'Deepseek V3'
                    })
                    log_message('SUCCESS', '✅ Added deepseek-v3 as alternative')
                else:
                    log_message('WARNING', '⚠️  No deepseek-v3 alternative found')
            except Exception as e:
                log_message('WARNING', f'⚠️  Could not check for deepseek-v3: {str(e)}')

        log_message('SUCCESS', f'🎯 Model selection complete!', {
            'Total available': len(largest_models),
            'Filtered out': filtered_count,
            'Final selection': len(selected_models)
        })

        return selected_models

    except Exception as e:
        log_message('ERROR', f'❌ Failed to load models: {str(e)}')
        return []

def query_single_model(model, user_message, chat_history):
    """Query a single model and return result with timing"""
    model_name = f"{model['provider']}/{model['model']}"
    log_message('INFO', f'🚀 Querying {model_name}...')
    
    try:
        start_time = time.time()

        response = px.generate_text(
            system="You are a helpful AI assistant. Be conversational and engaging.",
            messages=chat_history,
            provider_model=(model['provider'], model['model']),
            max_tokens=500,
            temperature=0.7
        )

        end_time = time.time()
        time_taken = round(end_time - start_time, 2)
        
        log_message('SUCCESS', f'✅ {model_name} responded successfully', {
            'Response time': f'{time_taken}s',
            'Response length': f'{len(response)} chars'
        })
        
        return {
            'model': model,
            'response': response,
            'time_taken': time_taken,
            'success': True
        }
    except Exception as e:
        end_time = time.time()
        time_taken = round(end_time - start_time, 2)
        
        log_message('ERROR', f'❌ {model_name} failed to respond', {
            'Error': str(e),
            'Time elapsed': f'{time_taken}s'
        })
        
        return {
            'model': model,
            'response': None,
            'time_taken': time_taken,
            'success': False,
            'error': str(e)
        }

def query_all_models_parallel(available_models, user_message, chat_history):
    """Query all models in parallel and return results"""
    log_message('INFO', f'🌟 Starting parallel query of {len(available_models)} models...')
    
    results = []
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(available_models)) as executor:
        # Submit all tasks
        future_to_model = {
            executor.submit(query_single_model, model, user_message, chat_history): model
            for model in available_models
        }

        log_message('INFO', f'📤 Submitted {len(future_to_model)} parallel requests')

        # Collect results as they complete
        completed_count = 0
        for future in concurrent.futures.as_completed(future_to_model):
            result = future.result()
            results.append(result)
            completed_count += 1
            
            model_name = f"{result['model']['provider']}/{result['model']['model']}"
            status = "✅" if result['success'] else "❌"
            log_message('INFO', f'{status} {completed_count}/{len(available_models)} models completed: {model_name}')

    total_time = round(time.time() - start_time, 2)
    successful_count = sum(1 for r in results if r['success'])
    failed_count = len(results) - successful_count
    
    log_message('SUCCESS', f'🏁 Parallel query completed!', {
        'Total time': f'{total_time}s',
        'Successful': successful_count,
        'Failed': failed_count,
        'Success rate': f'{(successful_count/len(results)*100):.1f}%'
    })

    return results

class ChatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global available_models
        client_ip = self.client_address[0]
        
        if self.path == '/':
            log_message('INFO', f'🌐 Serving main page to {client_ip}')
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open('index.html', 'r') as f:
                self.wfile.write(f.read().encode())
        elif self.path == '/style.css':
            log_message('INFO', f'🎨 Serving CSS to {client_ip}')
            self.send_response(200)
            self.send_header('Content-type', 'text/css')
            self.end_headers()
            with open('style.css', 'r') as f:
                self.wfile.write(f.read().encode())
        elif self.path == '/models':
            log_message('INFO', f'📋 Serving models list to {client_ip}', {
                'Available models': len(available_models)
            })
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'models': available_models}).encode())
        else:
            log_message('WARNING', f'❓ 404 request from {client_ip}: {self.path}')
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/chat':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            user_message = data.get('message', '').strip()
            selected_models = data.get('selected_models', [])
            combiner_model = data.get('combiner_model', {})

            if not user_message:
                response = {'error': 'Message cannot be empty'}
                self.send_response(400)
            elif not selected_models:
                response = {'error': 'No models selected'}
                self.send_response(400)
            elif not combiner_model:
                response = {'error': 'No combiner model selected'}
                self.send_response(400)
            else:
                try:
                    global chat_history
                    
                    log_message('INFO', f'💬 Received chat message from user', {
                        'Message length': f'{len(user_message)} chars',
                        'Selected models': len(selected_models),
                        'Combiner model': f"{combiner_model['provider']}/{combiner_model['model']}"
                    })
                    
                    chat_history.append({"role": "user", "content": user_message})

                    # Query selected models in parallel
                    start_total_time = time.time()
                    results = query_all_models_parallel(selected_models, user_message, chat_history)
                    total_time = round(time.time() - start_total_time, 2)

                    # Filter successful responses
                    successful_results = [r for r in results if r['success']]
                    failed_results = [r for r in results if not r['success']]

                    if successful_results:
                        log_message('SUCCESS', f'🎯 Preparing response combination', {
                            'Successful responses': len(successful_results),
                            'Failed responses': len(failed_results)
                        })
                        
                        # Create combining prompt
                        model_responses = []
                        for result in successful_results:
                            model_responses.append(f"Model: {result['model']['display_name']}\nResponse: {result['response']}")
                        
                        combining_prompt = f"""For the given chat history and the following responses from different AI models, compose one comprehensive answer to the user that synthesizes all important information from the different AI model responses. Respond naturally as if you are having a conversation, without mentioning that you are combining responses.

Query: {user_message}

{chr(10).join(model_responses)}"""
                        
                        # Add combining prompt to chat history for context
                        combiner_chat_history = chat_history + [{"role": "user", "content": combining_prompt}]
                        
                        # Query combiner model
                        combiner_name = f"{combiner_model['provider']}/{combiner_model['model']}"
                        log_message('INFO', f'🔗 Combining responses with {combiner_name}...')
                        
                        try:
                            start_combine_time = time.time()
                            combined_response = px.generate_text(
                                system="You are a helpful AI assistant. Synthesize information from multiple AI responses into one coherent, natural conversation response. Do not mention that you are combining responses - just provide a helpful, comprehensive answer.",
                                messages=combiner_chat_history,
                                provider_model=(combiner_model['provider'], combiner_model['model']),
                                max_tokens=800,
                                temperature=0.7
                            )
                            combine_time = round(time.time() - start_combine_time, 2)
                            
                            log_message('SUCCESS', f'✨ Response combination completed!', {
                                'Combiner time': f'{combine_time}s',
                                'Final response length': f'{len(combined_response)} chars',
                                'Total process time': f'{total_time + combine_time}s'
                            })
                            
                            chat_history.append({"role": "assistant", "content": combined_response})
                            response = {'response': combined_response}
                            self.send_response(200)
                            
                        except Exception as e:
                            log_message('ERROR', f'❌ Combiner model failed: {str(e)}')
                            log_message('WARNING', '🔄 Falling back to random response selection...')
                            
                            # Fallback to random selection if combiner fails
                            chosen_result = random.choice(successful_results)
                            chosen_response = chosen_result['response']
                            chosen_model = f"{chosen_result['model']['provider']}/{chosen_result['model']['model']}"
                            
                            log_message('SUCCESS', f'✅ Using fallback response from {chosen_model}', {
                                'Response length': f'{len(chosen_response)} chars'
                            })
                            
                            chat_history.append({"role": "assistant", "content": chosen_response})
                            response = {'response': chosen_response}
                            self.send_response(200)
                    else:
                        log_message('ERROR', '💥 All models failed to respond!')
                        response = {'error': 'All models failed to respond'}
                        self.send_response(500)

                except Exception as e:
                    log_message('ERROR', f'💥 Unexpected error in chat processing: {str(e)}')
                    response = {'error': 'Failed to get AI response'}
                    self.send_response(500)

            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

def run_server():
    global available_models
    log_message('INFO', '🚀 Starting Multi-Model AI Chat Server...')
    
    available_models = get_largest_models()
    
    if not available_models:
        log_message('ERROR', '💥 No models available! Cannot start server.')
        return

    server_address = ('localhost', 3000)
    httpd = HTTPServer(server_address, ChatHandler)
    
    log_message('SUCCESS', f'🌟 Server ready and listening!', {
        'URL': 'http://localhost:3000',
        'Models loaded': len(available_models),
        'Ready for connections': True
    })
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log_message('INFO', '⏹️  Server shutting down gracefully...')
        httpd.server_close()

if __name__ == '__main__':
    run_server()
