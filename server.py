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

def _get_log_colors():
    """Get color codes for log levels"""
    return {
        'INFO': '\033[94m',    # Blue
        'SUCCESS': '\033[92m', # Green
        'WARNING': '\033[93m', # Yellow
        'ERROR': '\033[91m',   # Red
        'RESET': '\033[0m'     # Reset
    }

def _format_log_details(details, color, reset):
    """Format log details for display"""
    if isinstance(details, dict):
        for key, value in details.items():
            print(f"         {color}├─{reset} {key}: {value}")
    elif isinstance(details, list):
        for item in details:
            print(f"         {color}├─{reset} {item}")
    else:
        print(f"         {color}└─{reset} {details}")

def log_message(level, message, details=None):
    """Pretty logging with timestamps and formatting"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    colors = _get_log_colors()
    color = colors.get(level, colors['RESET'])
    reset = colors['RESET']

    log_line = f"{color}[{timestamp}] {level:8} | {message}{reset}"
    print(log_line)

    if details:
        _format_log_details(details, color, reset)

def _should_skip_model(provider, model_name):
    """Check if a model should be skipped during selection"""
    return provider == 'deepseek' and model_name == 'deepseek-r1'

def _create_model_entry(provider, model_name):
    """Create a standardized model entry"""
    return {
        'provider': provider,
        'model': model_name,
        'display_name': f"{provider.title()} {model_name.replace('-', ' ').title()}"
    }

def _add_deepseek_v3_alternative(selected_models):
    """Add deepseek-v3 if no deepseek models are selected"""
    if any(m['provider'] == 'deepseek' for m in selected_models):
        return selected_models

    try:
        log_message('INFO', '🔍 Checking for deepseek-v3 alternative...')
        all_models = px.models.list_models()
        deepseek_v3 = next((m for m in all_models if m.provider == 'deepseek' and m.model == 'deepseek-v3'), None)
        if deepseek_v3:
            selected_models.append(_create_model_entry('deepseek', 'deepseek-v3'))
            log_message('SUCCESS', '✅ Added deepseek-v3 as alternative')
        else:
            log_message('WARNING', '⚠️  No deepseek-v3 alternative found')
    except Exception as e:
        log_message('WARNING', f'⚠️  Could not check for deepseek-v3: {str(e)}')

    return selected_models

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

            if _should_skip_model(provider, model_name):
                filtered_count += 1
                log_message('INFO', f'⚠️  Skipping {provider}/{model_name} (filtered out)')
                continue

            selected_models.append(_create_model_entry(provider, model_name))
            log_message('INFO', f'✅ Added model: {provider}/{model_name}')

        selected_models = _add_deepseek_v3_alternative(selected_models)

        log_message('SUCCESS', f'🎯 Model selection complete!', {
            'Total available': len(largest_models),
            'Filtered out': filtered_count,
            'Final selection': len(selected_models)
        })

        return selected_models

    except Exception as e:
        log_message('ERROR', f'❌ Failed to load models: {str(e)}')
        return []

def _create_success_result(model, response, time_taken):
    """Create a successful query result"""
    return {
        'model': model,
        'response': response,
        'time_taken': time_taken,
        'success': True
    }

def _create_error_result(model, error, time_taken):
    """Create a failed query result"""
    return {
        'model': model,
        'response': None,
        'time_taken': time_taken,
        'success': False,
        'error': str(error)
    }

def query_single_model(model, user_message, chat_history):
    """Query a single model and return result with timing"""
    model_name = f"{model['provider']}/{model['model']}"
    log_message('INFO', f'🚀 Querying {model_name}...')

    start_time = time.time()
    try:
        response = px.generate_text(
            system="You are a helpful AI assistant. Be conversational and engaging.",
            messages=chat_history,
            provider_model=(model['provider'], model['model']),
            max_tokens=500,
            temperature=0.7
        )

        time_taken = round(time.time() - start_time, 2)

        log_message('SUCCESS', f'✅ {model_name} responded successfully', {
            'Response time': f'{time_taken}s',
            'Response length': f'{len(response)} chars'
        })

        return _create_success_result(model, response, time_taken)

    except Exception as e:
        time_taken = round(time.time() - start_time, 2)

        log_message('ERROR', f'❌ {model_name} failed to respond', {
            'Error': str(e),
            'Time elapsed': f'{time_taken}s'
        })

        return _create_error_result(model, e, time_taken)

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

def _serve_file(handler, file_path, content_type, log_emoji, log_description):
    """Serve a static file with proper headers"""
    client_ip = handler.client_address[0]
    log_message('INFO', f'{log_emoji} {log_description} to {client_ip}')
    handler.send_response(200)
    handler.send_header('Content-type', content_type)
    handler.end_headers()
    with open(file_path, 'r') as f:
        handler.wfile.write(f.read().encode())

def _serve_models_json(handler):
    """Serve the models list as JSON"""
    global available_models
    client_ip = handler.client_address[0]
    log_message('INFO', f'📋 Serving models list to {client_ip}', {
        'Available models': len(available_models)
    })
    handler.send_response(200)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps({'models': available_models}).encode())

def _serve_404(handler):
    """Serve 404 error response"""
    client_ip = handler.client_address[0]
    log_message('WARNING', f'❓ 404 request from {client_ip}: {handler.path}')
    handler.send_response(404)
    handler.end_headers()

class ChatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            _serve_file(self, 'index.html', 'text/html', '🌐', 'Serving main page')
        elif self.path == '/style.css':
            _serve_file(self, 'style.css', 'text/css', '🎨', 'Serving CSS')
        elif self.path == '/models':
            _serve_models_json(self)
        else:
            _serve_404(self)

    def do_POST(self):
        if self.path == '/chat':
            _handle_chat_request(self)

def _parse_chat_request(handler):
    """Parse and validate chat request data"""
    content_length = int(handler.headers['Content-Length'])
    post_data = handler.rfile.read(content_length)
    data = json.loads(post_data.decode('utf-8'))

    return {
        'user_message': data.get('message', '').strip(),
        'selected_models': data.get('selected_models', []),
        'combiner_model': data.get('combiner_model', {})
    }

def _validate_chat_request(request_data):
    """Validate chat request and return error message if invalid"""
    if not request_data['user_message']:
        return 'Message cannot be empty'
    elif not request_data['selected_models']:
        return 'No models selected'
    elif not request_data['combiner_model']:
        return 'No combiner model selected'
    return None

def _create_combining_prompt(user_message, successful_results):
    """Create the prompt for combining multiple model responses"""
    model_responses = []
    for result in successful_results:
        model_responses.append(f"Model: {result['model']['display_name']}\nResponse: {result['response']}")

    return f"""Analyze the following responses from different AI models and provide a concise, structured summary that prioritizes the most valuable information:

1. FIRST: Identify the most common answer or consensus among the models
2. THEN: Only highlight truly valuable, unique insights that add significant value beyond the consensus
3. IMPORTANT: Skip any model contributions that are redundant, trivial, or don't add meaningful value

Query: {user_message}

Model Responses:
{chr(10).join(model_responses)}

Please format your response as follows:

**Summary of all models:** [Provide a clear, comprehensive summary of the consensus answer]

**Additional valuable insights:** (Only include if there are genuinely useful unique contributions)
- **[Model Name]:** [direct unique contribution without redundant phrases]
- **[Model Name]:** [another valuable unique insight]

IMPORTANT GUIDELINES:
- Keep the response concise and focused on the most useful information
- Only mention models in "Additional insights" if they provide genuinely valuable unique information
- If no models provide meaningful additional insights beyond the consensus, omit the "Additional insights" section entirely
- Prioritize quality over quantity - better to have fewer, more valuable insights than many trivial ones
- Do not repeat information already covered in the main summary"""

def _combine_responses_with_model(combiner_model, combiner_chat_history):
    """Use combiner model to synthesize responses"""
    combiner_name = f"{combiner_model['provider']}/{combiner_model['model']}"
    log_message('INFO', f'🔗 Combining responses with {combiner_name}...')

    start_combine_time = time.time()
    combined_response = px.generate_text(
        system="You are an expert AI response analyzer focused on extracting maximum value from multiple model outputs. Your key responsibilities: 1) Identify and summarize the consensus among models, 2) Filter out redundant or low-value information, 3) Only highlight truly valuable unique insights that add significant meaning beyond the consensus. Be selective and quality-focused - it's better to omit trivial contributions than to overcrowd the response. Prioritize clarity, conciseness, and genuine value.",
        messages=combiner_chat_history,
        provider_model=(combiner_model['provider'], combiner_model['model']),
        max_tokens=800,
        temperature=0.7
    )
    combine_time = round(time.time() - start_combine_time, 2)

    log_message('SUCCESS', f'✨ Response combination completed!', {
        'Combiner time': f'{combine_time}s',
        'Final response length': f'{len(combined_response)} chars'
    })

    return combined_response

def _fallback_to_random_response(successful_results):
    """Select a random response when combiner fails"""
    log_message('WARNING', '🔄 Falling back to random response selection...')

    chosen_result = random.choice(successful_results)
    chosen_response = chosen_result['response']
    chosen_model = f"{chosen_result['model']['provider']}/{chosen_result['model']['model']}"

    log_message('SUCCESS', f'✅ Using fallback response from {chosen_model}', {
        'Response length': f'{len(chosen_response)} chars'
    })

    return chosen_response

def _process_chat_models(request_data):
    """Process chat request with multiple models"""
    global chat_history

    user_message = request_data['user_message']
    selected_models = request_data['selected_models']
    combiner_model = request_data['combiner_model']

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

    if not successful_results:
        log_message('ERROR', '💥 All models failed to respond!')
        return {'error': 'All models failed to respond'}, 500

    log_message('SUCCESS', f'🎯 Preparing response combination', {
        'Successful responses': len(successful_results),
        'Failed responses': len(failed_results)
    })

    # Create combining prompt and get combined response
    combining_prompt = _create_combining_prompt(user_message, successful_results)
    combiner_chat_history = chat_history + [{"role": "user", "content": combining_prompt}]

    try:
        combined_response = _combine_responses_with_model(combiner_model, combiner_chat_history)
    except Exception as e:
        log_message('ERROR', f'❌ Combiner model failed: {str(e)}')
        combined_response = _fallback_to_random_response(successful_results)

    chat_history.append({"role": "assistant", "content": combined_response})
    return {'response': combined_response}, 200

def _send_json_response(handler, response_data, status_code):
    """Send JSON response with proper headers"""
    handler.send_response(status_code)
    handler.send_header('Content-type', 'application/json')
    handler.end_headers()
    handler.wfile.write(json.dumps(response_data).encode())

def _handle_chat_request(handler):
    """Handle the complete chat request flow"""
    try:
        request_data = _parse_chat_request(handler)
        error_message = _validate_chat_request(request_data)

        if error_message:
            _send_json_response(handler, {'error': error_message}, 400)
            return

        response_data, status_code = _process_chat_models(request_data)
        _send_json_response(handler, response_data, status_code)

    except Exception as e:
        log_message('ERROR', f'💥 Unexpected error in chat processing: {str(e)}')
        _send_json_response(handler, {'error': 'Failed to get AI response'}, 500)

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
