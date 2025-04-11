import os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
import asyncio
from google import genai
from concurrent.futures import TimeoutError

import json

# Load environment variables from .env file
load_dotenv()

# Access your API key and initialize Gemini client correctly
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

max_iterations = 15
last_response = None
iteration = 0
iteration_response = []

async def generate_with_timeout(client, prompt, timeout=10):
    """Generate content with a timeout"""
    print("Starting LLM generation...")
    try:
        # Convert the synchronous generate_content call to run in a thread
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None, 
                lambda: client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt
                )
            ),
            timeout=timeout
        )
        print("LLM generation completed")
        return response
    except TimeoutError:
        print("LLM generation timed out!")
        raise
    except Exception as e:
        print(f"Error in LLM generation: {e}")
        raise

def reset_state():
    """Reset all global variables to their initial state"""
    global last_response, iteration, iteration_response
    last_response = None
    iteration = 0
    iteration_response = []

async def main():
    reset_state()  # Reset at the start of main
    print("Starting main execution...")
    try:
        # Create a single MCP server connection
        print("Establishing connection to MCP server...")
        server_params = StdioServerParameters(
            command="python",
            args=["mcp_server.py"]
        )

        async with stdio_client(server_params) as (read, write):
            print("Connection established, creating session...")
            async with ClientSession(read, write) as session:
                print("Session created, initializing...")
                await session.initialize()
                
                # Get available tools
                tools_result = await session.list_tools()
                tools = tools_result.tools
                print(f"Successfully retrieved {len(tools)} tools")
            
                try:
                    tools_description = []
                    for i, tool in enumerate(tools):
                        try:
                            # Get tool properties
                            params = tool.inputSchema
                            desc = getattr(tool, 'description', 'No description available')
                            name = getattr(tool, 'name', f'tool_{i}')
                            
                            # Format the input schema in a more readable way
                            if 'properties' in params:
                                param_details = []
                                for param_name, param_info in params['properties'].items():
                                    param_type = param_info.get('type', 'unknown')
                                    param_details.append(f"{param_name}: {param_type}")
                                params_str = ', '.join(param_details)
                            else:
                                params_str = 'no parameters'

                            tool_desc = f"{i+1}. {name}({params_str}) - {desc}"
                            tools_description.append(tool_desc)
                            #print(f"Added description for tool: {tool_desc}")
                        except Exception as e:
                            print(f"Error processing tool {i}: {e}")
                            tools_description.append(f"{i+1}. Error processing tool")
                    
                    tools_description = "\n".join(tools_description)
                    print("Successfully created tools description")
                except Exception as e:
                    print(f"Error creating tools description: {e}")
                    tools_description = "Error loading tools"
                
                print("Created system prompt...")
                
                function_call = '{"type": "FUNCTION_CALL", "name": "function_name", "parameters": [param1, param2, ...], "reasoning_type": "type_of_reasoning"}'
                final_answer = '{"type": "FINAL_ANSWER", "final_answer": "number", "reasoning_type": "type_of_reasoning"}'
                
                example_step1 = 'User: Find the ASCII values of characters in INDIA and then return sum of exponentials of those values.'
                example_step2 = 'Assistant: {\'type\': \'FUNCTION_CALL\', \'name\': \'show_reasoning\', \'parameters\': [["Convert \'INDIA\' to ASCII values", \'Sum all exponential values\', \'Draw a rectangle from (200,300) to (800,800)\']], \'reasoning_type\': \'control\'}'
                example_step3 = 'User: What should i do next?'
                example_step4 = '\'Assistant: {\'type\': \'FUNCTION_CALL\', \'name\': \'strings_to_chars_to_int\', \'parameters\': [\'INDIA\'], \'reasoning_type\': \'lookup\'}'
                example_step5 = 'Result is [\'73\', \'78\', \'68\', \'73\', \'65\']. Lets Verify this step.'
                example_step6 = 'Assistant: {\'type\': \'FUNCTION_CALL\', \'name\': \'verify_string_to_int\', \'parameters\': [\'INDIA\', [73, 78, 68, 73, 65]]}'
                example_step7 = 'User: True received hence verified. What should i do next'
                example_step8 = 'Assistant: {\'type\': \'FUNCTION_CALL\', \'name\': \'int_list_to_exponential_sum\', \'parameters\': [[73, 78, 68, 73, 65]], \'reasoning_type\': \'arithmetic\'}'
                example_step9 = 'Result is [73, 78, 68, 73, 65]. Lets Verify this step.'
                example_step10 = 'Assistant: {\'type\': \'FUNCTION_CALL\', \'name\': \'verify_int_to_exponential_sum\', \'parameters\': [\'[73, 78, 68, 73, 65]\', \'7.59982224609308e+33\']}'
                example_step11 = 'User: True received hence verified. What should i do next'
                example_step12 = 'Assistant: {\'type\': \'FUNCTION_CALL\', \'name\': \'open_paint\', \'parameters\': [], \'reasoning_type\': \'drawing\'}'
                example_step13 = 'Result is \'Paint opened successfully and maximized\'. Lets Verify this step.'
                example_step14 = 'Assistant: {\'type\': \'FUNCTION_CALL\', \'name\': \'verify_open_paint\', \'parameters\': []}'
                example_step15 = 'User: True received hence verified. What should i do next'

                system_prompt = f"""You are a mathematical reasoning agent that solves problems step by step.
You have access to various tools.
Available tools:
{tools_description}

You must respond with EXACTLY ONE line in one of these formats (no additional text):
1. For function calls:
{function_call}

2. For final answers:
{final_answer}

Instructions:
- First Show the step-by-step reasoning process.
- After each FUNCTION_CALL, Verify result of each FUNCTION_CALL.
- Classify each step with "reasoning_type" (e.g., "lookup", "arithmetic", "trigonometric", "geometric", "string", "drawing", "control").
- Verify each result before using it. If a function output looks incorrect or out of expected range, repeat the call or choose an alternative.
- Before returning the final answer, re-calculate or cross-check it using a second method or sanity-check (e.g., check ranges, signs, or consistency).
- If a tool fails or returns an unexpected value, fallback to:
    - Retry with adjusted parameters (if possible),
    - Skip the step and note "reasoning_type": "fallback",
    - Or return a partial result with "final_answer": "UNKNOWN" and "reasoning_type": "error_handling".

Output Rules:
- Your entire response should be a single line JSON format, no newlines or spaces.
- Do not repeat function_call with the same parameters unless verifying.
- Do not include any explanations or additional text.

Format Examples:
- {example_step1}
- {example_step2}
- {example_step3}
- {example_step4}
- {example_step5}
- {example_step6}
- {example_step7}
- {example_step8}
- {example_step9}
- {example_step10}
- {example_step11}
- {example_step12}
- {example_step13}
- {example_step14}
- {example_step15}

"""

                query = """Find the ASCII values of characters in SHREYASH and then return sum of exponentials of those values. Once this is done, Inside MSPaint app, draw a rectangle (200,300,800,800) and write the final answer inside this rectangle."""
              
                # Use global iteration variables
                global iteration, last_response
                
                while iteration < max_iterations:
                    print(f"\n--- Iteration {iteration + 1} ---")
                    if last_response is None:
                        current_query = query
                    else:
                        current_query = current_query + "\n\n" + " ".join(iteration_response)

                    # Get model's response with timeout
                    print("Preparing to generate LLM response...")
                    prompt = f"{system_prompt}\n\nQuery: {current_query}\n\nWhat should I do next ? "
                    #print(f"Prompt: {prompt}")
                    try:
                        response = await generate_with_timeout(client, prompt)
                        response_text = json.loads(response.text.strip())
                        print(f"LLM Response: {response_text}")
                        
                    except Exception as e:
                        print(f"Failed to get LLM response: {e}")
                        break

                    if response_text['type'] == "FUNCTION_CALL":
                        func_name = response_text['name']
                        params = response_text['parameters']

                        print(f"DEBUG: Function name: {func_name}")
                        print(f"DEBUG: Parameters: {params}")

                        try:
                            # Find the matching tool to get its input schema
                            tool = next((t for t in tools if t.name == func_name), None)
                            if not tool:
                                print(f"DEBUG: Available tools: {[t.name for t in tools]}")
                                raise ValueError(f"Unknown tool: {func_name}")

                            print(f"DEBUG: Found tool: {tool.name}")
                            print(f"DEBUG: Tool schema: {tool.inputSchema}")

                            # Prepare arguments according to the tool's input schema
                            arguments = {}
                            schema_properties = tool.inputSchema.get('properties', {})

                            for param_name, param_info in schema_properties.items():
                                if not params:  # Check if we have enough parameters
                                    raise ValueError(f"Not enough parameters provided for {func_name}")
                                    
                                value = params.pop(0)  # Get and remove the first parameter
                                param_type = param_info.get('type', 'string')
                                
                                print(f"DEBUG: Converting parameter {param_name} with value {value} to type {param_type}")
                                
                                # Convert the value to the correct type based on the schema
                                if param_type == 'integer':
                                    arguments[param_name] = int(value)
                                elif param_type == 'number':
                                    arguments[param_name] = float(value)
                                elif param_type == 'array':
                                    # Handle array input
                                    if isinstance(value, str):
                                        value = value.strip('[]')
                                        elements = value.split(',')
                                        parsed_array = []
                                        for x in elements:
                                            x = x.strip()
                                            try:
                                                parsed_array.append(int(x))
                                            except ValueError:
                                                parsed_array.append(x)
                                        value = parsed_array

                                    arguments[param_name] = value
                                else:
                                    arguments[param_name] = str(value)

                            print(f"DEBUG: Final arguments: {arguments}")
                            print(f"DEBUG: Calling tool {func_name}")
                            
                            result = await session.call_tool(func_name, arguments=arguments)
                            print(f"DEBUG: Raw result: {result}")
                            
                            # Get the full result content
                            if hasattr(result, 'content'):
                                print(f"DEBUG: Result has content attribute")
                                # Handle multiple content items
                                if isinstance(result.content, list):
                                    iteration_result = [
                                        item.text if hasattr(item, 'text') else str(item)
                                        for item in result.content
                                    ]
                                else:
                                    iteration_result = str(result.content)
                            else:
                                print(f"DEBUG: Result has no content attribute")
                                iteration_result = str(result)
                                
                            print(f"DEBUG: Final iteration result: {iteration_result}")
                            
                            # Format the response based on result type
                            if isinstance(iteration_result, list):
                                result_str = f"[{', '.join(iteration_result)}]"
                            else:
                                result_str = str(iteration_result)
                            
                            iteration_response = []
                            iteration_response.append(
                                f"In the {iteration + 1} iteration you called {func_name} with {arguments} parameters, "
                                f"and the function returned {result_str}."
                            )
                            last_response = iteration_result

                        except Exception as e:
                            print(f"DEBUG: Error details: {str(e)}")
                            print(f"DEBUG: Error type: {type(e)}")
                            import traceback
                            traceback.print_exc()
                            iteration_response.append(f"Error in iteration {iteration + 1}: {str(e)}")
                            break

                    elif response_text['type'] == "FINAL_ANSWER":
                        print("\n=== Agent Execution Complete ===")
                        break

                    iteration += 1

    except Exception as e:
        print(f"Error in main execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        reset_state()  # Reset at the end of main

if __name__ == "__main__":
    asyncio.run(main())
    
    
