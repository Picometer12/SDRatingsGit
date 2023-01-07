This is unfinished and cobbled together by someone who doesn't know what they're doing. Use at your own risk. I haven't done much data validation yet, so leave batch count and batch size at 1 and type things carefully. 

# Using SDRatings

Dump SDRatings.py and the two folders into scripts folder of Automatic1111. Both folders contain editable text files.

Each line in SDRatings is currently in the format:
keywordName(Group1:rating1:numberOfTimesrated1,Group2:rating2)
the last colon and numberofTimesrated is optional and will be assumed to be 0 if missing. SDRatigns will update it the first time the keyword is rated.

ex: Anton Fadeev(Overall:2000:5, ConceptArtist:2200:5, CartoonArtist:1500)

To rate keywords, put keyword (literally type keyword) into your prompt, and put the group names in the rated groups field. When you generate, two keywords that have all groups listed will be selected, and the same prompts will be repeated except keyword will be replaced with keyword1 or keyword2. After generation, you can vote on whether you like left or right better and the ratings will be adjusted. Clicking Can't decide will generate two more sets of images with the same keywords and new seeds. 

AristList.xlsx is an excel spreadsheet that I used to help populate SDRatings.txt since I haven't built in anything for managing this in Automatic1111 yet. 


# Compatible with wildcards script
To use a wildcard, put __NameOfWildCardFile__ into your prompt and a random line from NameOfWildCardFile.txt in wildcards folder will be substituted.

# About Elo Ratings

I used [this article](https://mattmazzola.medium.com/understanding-the-elo-rating-system-264572c7a2b4) for the algorithm and default values for constants.

If the population of keywords were static and we didn't modify the Elo algorithm, the average keyword would be exactly 1500. However, if we introduce new keywords to the population and remove or stop rating the bad ones, 1500 will eventually become the average active keyword. As long as you keep ratings things, the best will be at the top, it might be worth keeping in time that a 2000 might turn into 1800 over time, and a rating that hasn't been bested in a long time may become inaccurate.  

# To Do
- Improve code quality if anyone ever wants to collaborate or contribute
- Add a gradio image near the vote buttons. As user generates images using the generate button, add the processed grids to a Queue that will feed into the new gradio image. This way you can generate a large batch of images and then come back and rate them back to back without waiting for images to generate.
- Add ways to add/remove keywords and groups
- Change all instances of group/groups to tag/tags, which might be a more intuitive name
- Have different modes for comparison. Instead of always assigning opponents randomly, have a mode for sorted list. 
  - Randomized (current setting) is good for keywords that are vastly underrated or overrated, but using a sorted list or +- 400 rating points would generally be better.
  - Setting up a round robin -> double elim tournament would be time consuming with a lot of keywords, but might be a good way to build a strong prompt at the same time you're updating ratings.
  - On that note, any mode that will serve another purpose but produce valid comparisons in the end would make updating ratings much less of a chore. 
- Add the keyword to the start of the prompt if "keyword" is not present in the prompt
- Add a mode for rating a new keyword a large number of times against many keywords that already have mature ratings for rating new keywords quickly
- Give credit to the right wildcards script and provide a link. Or upgrade to the newest one if it has more functionality.
- Think about case where one group's is a subset of another group's name

